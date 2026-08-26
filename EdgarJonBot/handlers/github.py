"""/gh — GitHub connector commands and the polling job."""
import html
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

import db
import github as gh

log = logging.getLogger("edgarjon.gh")


async def gh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat_id = update.effective_chat.id
    args = context.args or []
    sub = args[0].lower() if args else ""
    if not gh.enabled():
        await msg.reply_text("GitHub isn't connected — set GITHUB_TOKEN (or `gh auth login`) on the host and restart me.")
        return
    if sub == "watch" and len(args) == 2:
        repo = gh.parse_repo(args[1])
        if not repo:
            await msg.reply_text(
                f"I need owner/repo, not just an owner — e.g. /gh watch {args[1].strip('/')}/JonTeleGameBot"
                if "/" not in args[1] else "Usage: /gh watch owner/repo"
            )
            return
        info = await gh.repo_info(repo)
        if not info:
            await msg.reply_text(f"Can't see {repo} — typo, or my token can't read it.")
            return
        added = db.gh_watch(chat_id, repo, update.effective_user.first_name)
        if added:
            # Start from now: don't replay history into the chat.
            evs, etag = await gh.events(repo, None)
            if evs:
                db.gh_set(repo, "last_id", max(int(e["id"]) for e in evs))
            if etag:
                db.gh_set(repo, "etag", etag)
        await msg.reply_html(
            f"👀 Watching <b>{html.escape(info['full_name'])}</b>" + (" (already was)." if not added else ".") +
            f" ⭐{info.get('stargazers_count', 0)} · {info.get('open_issues_count', 0)} open issues · default <code>{html.escape(info.get('default_branch', 'main'))}</code>"
        )
        return
    if sub == "unwatch" and len(args) == 2:
        repo = gh.parse_repo(args[1]) or ""
        await msg.reply_text("Unwatched." if db.gh_unwatch(chat_id, repo) else "Wasn't watching that.")
        return
    if sub in ("list", ""):
        rows = db.gh_watched(chat_id)
        logins = db.gh_logins(chat_id)
        if not rows:
            await msg.reply_text("Not watching anything. /gh watch owner/repo to start; /gh me <login> to link your GitHub.")
            return
        lines = ["👀 <b>Watching</b>"] + [f"• {html.escape(r['repo'])}" for r in rows]
        if logins:
            lines.append("\n🔗 " + ", ".join(f"{html.escape(u['name'])} = {html.escape(u['login'])}" for u in logins))
        lines.append("\n/prs · /gh watch|unwatch owner/repo · /gh me &lt;login&gt; · /gh owner/repo")
        await msg.reply_html("\n".join(lines))
        return
    if sub == "me" and len(args) == 2:
        u = update.effective_user
        db.gh_link(chat_id, u.id, u.first_name, args[1].lstrip("@"))
        await msg.reply_text(f"Linked: {u.first_name} is @{args[1].lstrip('@')} on GitHub. Merged PRs will land in /shipped automatically.")
        return
    repo = gh.parse_repo(args[0])
    if repo:
        info = await gh.repo_info(repo)
        if not info:
            await msg.reply_text("Can't see that repo.")
            return
        pulls = await gh.open_pulls(repo)
        sha, ci = await gh.head_checks(repo, info.get("default_branch", "main"))
        ci_icon = {"success": "✅", "failure": "❌", "pending": "⏳"}.get(ci, "—")
        lines = [
            f"<b>{html.escape(info['full_name'])}</b> — {html.escape(info.get('description') or '')}".rstrip(" —"),
            f"⭐{info.get('stargazers_count', 0)} · {info.get('open_issues_count', 0)} open issues · {len(pulls)} open PRs · CI {ci_icon}",
            f"last push {html.escape((info.get('pushed_at') or '')[:10])} · <a href=\"{html.escape(info['html_url'])}\">open</a>",
        ]
        lines += gh.format_pr_list(repo, pulls[:5])
        await msg.reply_html("\n".join(lines), disable_web_page_preview=True)
        return
    await msg.reply_text("/gh watch owner/repo · /gh unwatch owner/repo · /gh list · /gh me <login> · /gh owner/repo · /prs")


async def prs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rows = db.gh_watched(chat_id)
    if not rows:
        await update.effective_message.reply_text("Watch a repo first: /gh watch owner/repo")
        return
    lines = ["🔀 <b>Open PRs</b>"]
    total = 0
    for r in rows:
        pulls = await gh.open_pulls(r["repo"])
        total += len(pulls)
        lines += gh.format_pr_list(r["repo"], pulls)
    if total == 0:
        lines.append("None. Suspiciously tidy.")
    await update.effective_message.reply_html("\n".join(lines), disable_web_page_preview=True)


# ------------------------------------------------------------------ writes

def _split_title_body(text: str) -> tuple[str, str]:
    title, _, body = text.partition("|")
    return title.strip()[:200], body.strip()


def _linked(chat_id: int, user) -> str | None:
    row = None
    for u in db.gh_logins(chat_id):
        if u["user_id"] == user.id:
            row = u
    return row["login"] if row else None


async def pr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/pr owner/repo head [base] | title | body  ·  /pr approve owner/repo#n  ·  /pr merge owner/repo#n"""
    msg = update.effective_message
    chat_id = update.effective_chat.id
    user = update.effective_user
    if not gh.enabled():
        await msg.reply_text("GitHub isn't connected.")
        return
    login = _linked(chat_id, user)
    if not login:
        await msg.reply_text("Link your GitHub first: /gh me <login> — writes are attributed, so I want to know who's asking.")
        return
    raw = " ".join(context.args or [])
    if not raw:
        await msg.reply_text(
            "/pr owner/repo head-branch [base] | title | body — open a PR from an existing branch\n"
            "/pr approve owner/repo#12 [comment] · /pr merge owner/repo#12 [squash|merge|rebase]\n"
            "/issue owner/repo title | body"
        )
        return
    words = raw.split()
    sub = words[0].lower()
    if sub in ("approve", "merge") and len(words) >= 2:
        ref = gh.parse_pr_ref(words[1])
        if not ref:
            await msg.reply_text("Which PR? owner/repo#12 or a PR link.")
            return
        repo, num = ref
        pr = await gh.get_pull(repo, num)
        if not pr:
            await msg.reply_text("Can't find that PR.")
            return
        if sub == "approve":
            ok, err = await gh.review_pull(repo, num, "APPROVE", " ".join(words[2:]) or f"Approved from Telegram by {login}")
            await msg.reply_html(f"👍 Approved <a href=\"{html.escape(pr['html_url'])}\">{html.escape(repo.split('/')[-1])}#{num}</a>." if ok else f"GitHub said no: {html.escape(err)}")
            return
        method = words[2].lower() if len(words) > 2 and words[2].lower() in ("squash", "merge", "rebase") else "squash"
        if pr.get("merged"):
            await msg.reply_text("Already merged.")
            return
        if pr.get("mergeable") is False:
            await msg.reply_text("GitHub says it isn't mergeable (conflicts?). Fix that first.")
            return
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✅ {method} merge #{num}", callback_data=f"ghm:{user.id}:{method}:{repo}#{num}"),
            InlineKeyboardButton("Cancel", callback_data=f"ghm:{user.id}:cancel:{repo}#{num}"),
        ]])
        await msg.reply_html(
            f"Merge <a href=\"{html.escape(pr['html_url'])}\">{html.escape(repo.split('/')[-1])}#{num}</a> "
            f"<b>{html.escape(pr['title'])}</b> ({html.escape(pr['head']['ref'])} → {html.escape(pr['base']['ref'])}) via {method}?",
            reply_markup=kb, disable_web_page_preview=True,
        )
        return
    # create: owner/repo head [base] | title | body
    head_part, title, body = (raw.split("|") + ["", ""])[:3] if "|" in raw else (raw, "", "")
    parts = head_part.split()
    repo = gh.parse_repo(parts[0]) if parts else None
    if not repo or len(parts) < 2 or not title.strip():
        await msg.reply_text("Usage: /pr owner/repo head-branch [base] | title | body")
        return
    head = parts[1]
    base = parts[2] if len(parts) > 2 else db.gh_get(repo, "default_branch") or (await gh.repo_info(repo) or {}).get("default_branch", "main")
    names = await gh.branches(repo)
    if names and head not in names:
        close = [n for n in names if head.lower() in n.lower()][:5]
        await msg.reply_text(f"No branch “{head}” in {repo}." + (f" Did you mean: {', '.join(close)}" if close else f" Branches: {', '.join(names[:10])}"))
        return
    body_text = (body.strip() + f"\n\n_Opened from Telegram by @{login}._").strip()
    pr, err = await gh.create_pull(repo, head, base, title.strip(), body_text)
    if not pr:
        await msg.reply_text(f"GitHub said no: {err}")
        return
    db.gh_log_activity(chat_id, f"{login} opened PR #{pr['number']} in {repo.split('/')[-1]}: {title.strip()}")
    await msg.reply_html(f"🔀 Opened <a href=\"{html.escape(pr['html_url'])}\">{html.escape(repo.split('/')[-1])}#{pr['number']}</a>: {html.escape(title.strip())} ({html.escape(head)} → {html.escape(base)})", disable_web_page_preview=True)


async def issue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat_id = update.effective_chat.id
    user = update.effective_user
    login = _linked(chat_id, user)
    if not gh.enabled() or not login:
        await msg.reply_text("Link your GitHub first: /gh me <login>")
        return
    raw = " ".join(context.args or [])
    parts = raw.split(maxsplit=1)
    repo = gh.parse_repo(parts[0]) if parts else None
    if not repo or len(parts) < 2:
        await msg.reply_text("Usage: /issue owner/repo title | body")
        return
    title, body = _split_title_body(parts[1])
    if not title:
        await msg.reply_text("Usage: /issue owner/repo title | body")
        return
    iss, err = await gh.create_issue(repo, title, (body + f"\n\n_Filed from Telegram by @{login}._").strip())
    if not iss:
        await msg.reply_text(f"GitHub said no: {err}")
        return
    db.gh_log_activity(chat_id, f"{login} opened issue #{iss['number']} in {repo.split('/')[-1]}: {title}")
    await msg.reply_html(f"🐛 Opened <a href=\"{html.escape(iss['html_url'])}\">{html.escape(repo.split('/')[-1])}#{iss['number']}</a>: {html.escape(title)}", disable_web_page_preview=True)


async def merge_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    _, owner, method, ref = q.data.split(":", 3)
    if q.from_user.id != int(owner):
        await q.answer("Not your merge button.")
        return
    await q.answer()
    if method == "cancel":
        await q.edit_message_text("Merge cancelled.")
        return
    repo, num = gh.parse_pr_ref(ref)
    ok, err = await gh.merge_pull(repo, num, method)
    if ok:
        login = _linked(q.message.chat_id, q.from_user) or q.from_user.first_name
        db.gh_log_activity(q.message.chat_id, f"{login} merged PR #{num} in {repo.split('/')[-1]} via {method}")
        await q.edit_message_text(f"✅ Merged {repo.split('/')[-1]}#{num} ({method}).")
    else:
        await q.edit_message_text(f"Merge failed: {err}")


# ------------------------------------------------------------------ polling

async def poll(context: ContextTypes.DEFAULT_TYPE):
    if not gh.enabled():
        return
    watched = db.gh_watched()
    by_repo: dict[str, list[int]] = {}
    for r in watched:
        by_repo.setdefault(r["repo"], []).append(r["chat_id"])
    for repo, chats in by_repo.items():
        try:
            await _poll_repo(context, repo, chats)
        except Exception:
            log.exception("poll failed for %s", repo)


async def _poll_repo(context, repo: str, chats: list[int]):
    evs, etag = await gh.events(repo, db.gh_get(repo, "etag"))
    if evs is None:
        return
    if etag:
        db.gh_set(repo, "etag", etag)
    fresh = gh.new_events(evs, db.gh_get(repo, "last_id"))
    lines_html, lines_plain = [], []
    for ev in fresh:
        if ev.get("type") == "PushEvent":
            ev = await gh.enrich_push(repo, ev)
        f = gh.format_event(ev)
        if f:
            lines_html.append(f[0])
            lines_plain.append(f[1])
        pr = gh.merged_pr(ev)
        if pr:
            login = (pr.get("user") or {}).get("login", "")
            for chat_id in chats:
                u = db.gh_user_for_login(chat_id, login)
                if u:
                    db.add_shipped(chat_id, u["user_id"], u["name"], f"merged {repo.split('/')[-1]}#{pr.get('number')}: {pr.get('title')}")
    if fresh:
        db.gh_set(repo, "last_id", max(int(e["id"]) for e in fresh))
    # CI on the default branch: announce a failure once per sha, and the recovery.
    info_branch = db.gh_get(repo, "default_branch")
    if not info_branch:
        info = await gh.repo_info(repo)
        info_branch = (info or {}).get("default_branch", "main")
        db.gh_set(repo, "default_branch", info_branch)
    sha, ci = await gh.head_checks(repo, info_branch)
    if sha and ci in ("success", "failure"):
        prev = db.gh_get(repo, "ci_state")
        if prev != f"{sha}:{ci}":
            prev_ci = (prev or "").split(":")[-1]
            if ci == "failure":
                lines_html.append(f"❌ CI is <b>failing</b> on {html.escape(repo.split('/')[-1])}:{html.escape(info_branch)} at <code>{sha[:7]}</code>")
                lines_plain.append(f"CI failing on {repo} {info_branch} at {sha[:7]}")
            elif prev_ci == "failure":
                lines_html.append(f"✅ CI is green again on {html.escape(repo.split('/')[-1])}:{html.escape(info_branch)}")
                lines_plain.append(f"CI green again on {repo}")
            db.gh_set(repo, "ci_state", f"{sha}:{ci}")
    if not lines_html:
        return
    text = "\n".join(lines_html[-12:])
    if len(lines_html) > 12:
        text = f"<i>…{len(lines_html) - 12} earlier events</i>\n" + text
    for chat_id in chats:
        for line in lines_plain:
            db.gh_log_activity(chat_id, line)
        try:
            await context.bot.send_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            log.warning("send to %s failed: %s", chat_id, e)


def schedule(app: Application):
    import config
    app.job_queue.run_repeating(poll, interval=config.GITHUB_POLL_SECONDS, first=30, name="github-poll")


def get_handlers():
    return [
        CommandHandler("gh", gh_cmd),
        CommandHandler(["prs", "pulls"], prs_cmd),
        CommandHandler("pr", pr_cmd),
        CommandHandler("issue", issue_cmd),
        CallbackQueryHandler(merge_callback, pattern=r"^ghm:\d+:"),
    ]
