"""GitHub connector. The bot has no public URL, so it polls the REST API:
per-repo event feeds (pushes, PRs, issues, releases) plus check-runs on the
default branch for CI failures. Read-only; needs a token with repo scope."""
import html
import json
import logging
import subprocess

import httpx

import config

log = logging.getLogger("edgarjon.github")
API = "https://api.github.com"
_token_cache: str | None = None


def token() -> str:
    global _token_cache
    if _token_cache is None:
        t = config.GITHUB_TOKEN
        if not t:
            try:
                t = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10).stdout.strip()
            except Exception:
                t = ""
        _token_cache = t
    return _token_cache


def enabled() -> bool:
    return bool(token())


async def _send(method: str, path: str, body: dict | None = None):
    """Write call. Returns (status, json)."""
    headers = {"Authorization": f"Bearer {token()}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.request(method, API + path, json=body, headers=headers)
    try:
        j = r.json()
    except Exception:
        j = {}
    if r.status_code >= 400:
        log.warning("github %s %s -> %s %s", method, path, r.status_code, str(j)[:200])
    return r.status_code, j


def error_text(j: dict) -> str:
    msg = j.get("message", "unknown error")
    details = "; ".join(
        e.get("message") or f"{e.get('field', '?')} {e.get('code', '')}".strip()
        for e in j.get("errors", []) if isinstance(e, dict)
    )
    return f"{msg}" + (f" — {details}" if details else "")


async def branches(repo: str) -> list[str]:
    st, j, _ = await _get(f"/repos/{repo}/branches", {"per_page": 50})
    return [b["name"] for b in (j or [])] if st == 200 else []


async def create_pull(repo: str, head: str, base: str, title: str, body: str) -> tuple[dict | None, str]:
    st, j = await _send("POST", f"/repos/{repo}/pulls", {"title": title, "head": head, "base": base, "body": body})
    return (j, "") if st == 201 else (None, error_text(j))


async def create_issue(repo: str, title: str, body: str) -> tuple[dict | None, str]:
    st, j = await _send("POST", f"/repos/{repo}/issues", {"title": title, "body": body})
    return (j, "") if st == 201 else (None, error_text(j))


async def get_pull(repo: str, number: int) -> dict | None:
    st, j, _ = await _get(f"/repos/{repo}/pulls/{number}")
    return j if st == 200 else None


async def review_pull(repo: str, number: int, event: str, body: str = "") -> tuple[bool, str]:
    st, j = await _send("POST", f"/repos/{repo}/pulls/{number}/reviews", {"event": event, "body": body})
    return (True, "") if st == 200 else (False, error_text(j))


async def merge_pull(repo: str, number: int, method: str = "squash") -> tuple[bool, str]:
    st, j = await _send("PUT", f"/repos/{repo}/pulls/{number}/merge", {"merge_method": method})
    return (st == 200, "" if st == 200 else error_text(j))


def parse_pr_ref(arg: str) -> tuple[str, int] | None:
    """'owner/repo#12' or a PR URL → (repo, number)."""
    arg = arg.strip().removeprefix("https://github.com/")
    if "/pull/" in arg:
        repo, _, num = arg.partition("/pull/")
        num = num.split("/")[0]
    elif "#" in arg:
        repo, _, num = arg.partition("#")
    else:
        return None
    r = parse_repo(repo)
    return (r, int(num)) if r and num.isdigit() else None


async def _get(path: str, params: dict | None = None, etag: str | None = None):
    """Returns (status, json, etag). 304 → (304, None, etag)."""
    headers = {"Authorization": f"Bearer {token()}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    if etag:
        headers["If-None-Match"] = etag
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(API + path, params=params, headers=headers)
    if r.status_code == 304:
        return 304, None, etag
    if r.status_code >= 400:
        log.warning("github %s -> %s %s", path, r.status_code, r.text[:120])
        return r.status_code, None, None
    return r.status_code, r.json(), r.headers.get("ETag")


async def repo_info(repo: str) -> dict | None:
    st, j, _ = await _get(f"/repos/{repo}")
    return j if st == 200 else None


async def events(repo: str, etag: str | None) -> tuple[list[dict] | None, str | None]:
    st, j, new_etag = await _get(f"/repos/{repo}/events", {"per_page": 50}, etag)
    if st == 304:
        return [], etag
    return (j if st == 200 else None), new_etag


async def enrich_push(repo: str, ev: dict) -> dict:
    """The events feed no longer inlines commits; fill payload['commits'] from a compare call."""
    p = ev.get("payload") or {}
    if p.get("commits") or not p.get("head"):
        return ev
    before = p.get("before")
    if before and before != "0" * 40:
        st, j, _ = await _get(f"/repos/{repo}/compare/{before}...{p['head']}", {"per_page": 30})
        commits = [{"message": (c.get("commit") or {}).get("message", "")} for c in (j or {}).get("commits", [])] if st == 200 else []
        if st == 200 and (j or {}).get("total_commits", len(commits)) > len(commits):
            commits += [{"message": ""}] * ((j or {})["total_commits"] - len(commits))
    else:
        st, j, _ = await _get(f"/repos/{repo}/commits/{p['head']}")
        commits = [{"message": (j.get("commit") or {}).get("message", "")}] if st == 200 and j else []
    ev["payload"] = {**p, "commits": commits}
    return ev


async def open_pulls(repo: str) -> list[dict]:
    st, j, _ = await _get(f"/repos/{repo}/pulls", {"state": "open", "per_page": 20})
    return j or []


async def head_checks(repo: str, ref: str) -> tuple[str | None, str]:
    """(sha, conclusion) for the latest commit on ref: 'success' | 'failure' | 'pending' | 'none'."""
    st, j, _ = await _get(f"/repos/{repo}/commits/{ref}/check-runs", {"per_page": 50})
    if st != 200 or not j:
        return None, "none"
    runs = j.get("check_runs") or []
    if not runs:
        return None, "none"
    sha = runs[0].get("head_sha")
    concl = {r.get("conclusion") for r in runs}
    if any(r.get("status") != "completed" for r in runs):
        return sha, "pending"
    if concl & {"failure", "timed_out", "cancelled"}:
        return sha, "failure"
    return sha, "success"


# ------------------------------------------------------------- formatting

def _e(s) -> str:
    return html.escape(str(s or ""))


def format_event(ev: dict) -> tuple[str, str] | None:
    """(html line, plain line) for one GitHub event, or None if it's noise.
    Pure — used by tests."""
    t = ev.get("type")
    p = ev.get("payload") or {}
    actor = _e((ev.get("actor") or {}).get("login"))
    repo = (ev.get("repo") or {}).get("name", "")
    short = repo.split("/")[-1]
    url = f"https://github.com/{repo}"
    if t == "PushEvent":
        ref = (p.get("ref") or "").replace("refs/heads/", "")
        commits = p.get("commits") or []
        n = len(commits)
        if n == 0:
            return None
        first = _e((commits[-1].get("message") or "").splitlines()[0][:80])
        more = f" (+{n - 1} more)" if n > 1 else ""
        sha = (p.get("head") or "")[:7]
        return (f"⬆️ <b>{actor}</b> pushed to <a href=\"{url}/commits/{_e(ref)}\">{_e(short)}:{_e(ref)}</a> — {first}{more} <code>{sha}</code>",
                f"{actor} pushed to {short}:{ref}: {first}{more}")
    if t == "PullRequestEvent":
        pr = p.get("pull_request") or {}
        act = p.get("action")
        num, title = pr.get("number"), _e(pr.get("title"))
        link = f"<a href=\"{_e(pr.get('html_url'))}\">#{num}</a>"
        if act == "opened":
            return f"🔀 <b>{actor}</b> opened PR {link} in {_e(short)}: {title}", f"{actor} opened PR #{num} in {short}: {title}"
        if act == "closed" and pr.get("merged"):
            return f"✅ <b>{actor}</b> merged PR {link} in {_e(short)}: {title}", f"{actor} merged PR #{num} in {short}: {title}"
        if act == "closed":
            return f"🚫 <b>{actor}</b> closed PR {link} in {_e(short)} without merging: {title}", f"{actor} closed PR #{num} in {short}"
        if act == "reopened":
            return f"♻️ <b>{actor}</b> reopened PR {link} in {_e(short)}", f"{actor} reopened PR #{num} in {short}"
        return None
    if t == "PullRequestReviewEvent":
        pr = p.get("pull_request") or {}
        state = (p.get("review") or {}).get("state", "")
        icon = {"approved": "👍", "changes_requested": "✍️"}.get(state)
        if not icon:
            return None
        return (f"{icon} <b>{actor}</b> {_e(state.replace('_', ' '))} on PR <a href=\"{_e(pr.get('html_url'))}\">#{pr.get('number')}</a> in {_e(short)}",
                f"{actor} {state} PR #{pr.get('number')} in {short}")
    if t == "IssuesEvent":
        iss = p.get("issue") or {}
        act = p.get("action")
        if act not in ("opened", "closed"):
            return None
        icon = "🐛" if act == "opened" else "🎉"
        return (f"{icon} <b>{actor}</b> {act} issue <a href=\"{_e(iss.get('html_url'))}\">#{iss.get('number')}</a> in {_e(short)}: {_e(iss.get('title'))}",
                f"{actor} {act} issue #{iss.get('number')} in {short}: {iss.get('title')}")
    if t == "ReleaseEvent" and p.get("action") == "published":
        rel = p.get("release") or {}
        return (f"🚀 <b>{actor}</b> released <a href=\"{_e(rel.get('html_url'))}\">{_e(rel.get('tag_name'))}</a> of {_e(short)}",
                f"{actor} released {rel.get('tag_name')} of {short}")
    if t == "CreateEvent" and p.get("ref_type") == "branch":
        return f"🌱 <b>{actor}</b> created branch <code>{_e(p.get('ref'))}</code> in {_e(short)}", f"{actor} created branch {p.get('ref')} in {short}"
    if t == "DeleteEvent" and p.get("ref_type") == "branch":
        return f"🪓 <b>{actor}</b> deleted branch <code>{_e(p.get('ref'))}</code> in {_e(short)}", f"{actor} deleted branch {p.get('ref')} in {short}"
    return None


def merged_pr(ev: dict) -> dict | None:
    """The PR dict if this event is a merge, else None."""
    if ev.get("type") != "PullRequestEvent":
        return None
    p = ev.get("payload") or {}
    pr = p.get("pull_request") or {}
    return pr if p.get("action") == "closed" and pr.get("merged") else None


def new_events(evs: list[dict], last_id: str | None) -> list[dict]:
    """Events newer than last_id, oldest first. Event ids are increasing strings of digits."""
    fresh = [e for e in evs if last_id is None or int(e["id"]) > int(last_id)]
    return sorted(fresh, key=lambda e: int(e["id"]))


def format_pr_list(repo: str, pulls: list[dict]) -> list[str]:
    short = repo.split("/")[-1]
    out = []
    for pr in pulls:
        who = _e((pr.get("user") or {}).get("login"))
        reviewers = ", ".join(_e(r.get("login")) for r in pr.get("requested_reviewers") or [])
        draft = " (draft)" if pr.get("draft") else ""
        wait = f" — waiting on {reviewers}" if reviewers else ""
        out.append(f"• <a href=\"{_e(pr.get('html_url'))}\">{_e(short)}#{pr.get('number')}</a> {_e(pr.get('title'))}{draft} <i>by {who}{wait}</i>")
    return out


def parse_repo(arg: str) -> str | None:
    arg = arg.strip().removeprefix("https://github.com/").removesuffix(".git").strip("/")
    parts = arg.split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return f"{parts[0]}/{parts[1]}".lower()


async def readme(repo: str) -> str:
    st, j, _ = await _get(f"/repos/{repo}/readme")
    if st != 200 or not j:
        return ""
    import base64
    try:
        return base64.b64decode(j.get("content", "")).decode("utf-8", "replace")
    except Exception:
        return ""


async def tree(repo: str, branch: str, limit=80) -> list[str]:
    st, j, _ = await _get(f"/repos/{repo}/git/trees/{branch}", {"recursive": "1"})
    if st != 200 or not j:
        return []
    paths = [t["path"] for t in j.get("tree", []) if t.get("type") == "blob"]
    noise = ("node_modules/", ".git/", "dist/", "build/", "__pycache__/", ".lock", ".png", ".jpg", ".svg", ".ico")
    paths = [p for p in paths if not any(n in p for n in noise)]
    # Prefer shallow, structural files.
    paths.sort(key=lambda p: (p.count("/"), p))
    return paths[:limit]


async def languages(repo: str) -> list[str]:
    st, j, _ = await _get(f"/repos/{repo}/languages")
    return [k for k, _ in sorted((j or {}).items(), key=lambda kv: -kv[1])][:4] if st == 200 else []


async def recent_commits(repo: str, n=10) -> list[str]:
    st, j, _ = await _get(f"/repos/{repo}/commits", {"per_page": n})
    if st != 200 or not j:
        return []
    return [f"{c['sha'][:7]} {(c.get('commit') or {}).get('message', '').splitlines()[0][:80]}" for c in j]


async def build_card(repo: str) -> str:
    """A compact, prompt-ready description of a repo: what, how it's built, where things live."""
    info = await repo_info(repo)
    if not info:
        return ""
    branch = info.get("default_branch", "main")
    rd, paths, langs, commits = await readme(repo), await tree(repo, branch), await languages(repo), await recent_commits(repo)
    rd = " ".join(rd.split())[:2500]
    lines = [f"REPO {info['full_name']} — {info.get('description') or 'no description'} · {', '.join(langs) or 'unknown languages'} · default {branch} · last push {(info.get('pushed_at') or '')[:10]}"]
    if rd:
        lines.append("README: " + rd)
    if paths:
        lines.append("Files: " + ", ".join(paths))
    if commits:
        lines.append("Recent commits: " + " | ".join(commits))
    return "\n".join(lines)[:6000]


async def file_content(repo: str, path: str, ref: str | None = None) -> tuple[str | None, str]:
    st, j, _ = await _get(f"/repos/{repo}/contents/{path.strip('/')}", {"ref": ref} if ref else None)
    if st != 200 or not j:
        return None, "not found"
    if isinstance(j, list):
        return None, "that's a directory: " + ", ".join(x["name"] for x in j[:40])
    if j.get("encoding") != "base64":
        return None, "can't read that (too large or binary)"
    import base64
    try:
        return base64.b64decode(j.get("content", "")).decode("utf-8", "replace"), ""
    except Exception:
        return None, "binary file"
