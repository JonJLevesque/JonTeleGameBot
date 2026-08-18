"""Static prompt banks for the party games.

Any prompt containing "{subject}" is formatted with the name of a random
other chat member before being sent. House rule for every bank: prompts that
involve people are about members of THIS chat — no outside crushes, partners,
or contacts.

Banks come in three flavors per category, assembled by pool():
  *          — works at any chat size
  *_GROUP    — only makes sense with 3+ members ("who in this chat…")
  *_DUO      — written for exactly two people, where {subject} is always
               the one other person
"""

TRUTHS = [
    "What's the most embarrassing thing you've ever said to someone in this chat?",
    "What's a secret talent nobody in this chat knows about?",
    "What's the longest you've gone without showering?",
    "What's the most childish thing you still do?",
    "Have you ever pretended to be sick to skip something? What was it?",
    "What's the worst gift you've ever received, and did you pretend to like it?",
    "What's your most-used emoji and what does that say about you?",
    "What's the last lie you told?",
    "What's the weirdest thing you've ever eaten?",
    "What's a movie you pretend to have seen?",
    "What's the most money you've spent on something completely useless?",
    "What's your guilty-pleasure song?",
    "What's the pettiest thing you've ever done?",
    "What's a food opinion you have that everyone disagrees with?",
    "What's the worst haircut you've ever had?",
    "What app on your phone would you be embarrassed to show your screen time for?",
    "What's something you believed way too long as a kid?",
    "Have you ever sent a text to the wrong person? What did it say?",
    "What's your worst kitchen disaster?",
    "What's the cringiest phase you've ever gone through?",
    "If your search history from last week were read aloud, what would be the worst entry?",
    "What's the strangest dream you remember?",
    "What's one thing you'd change about your personality if you could?",
    "What's the longest you've kept a piece of clothing without washing it?",
    "Have you ever laughed at something you really shouldn't have? What was it?",
    "What's your most irrational fear?",
    "What's one opinion of {subject}'s that you secretly disagree with?",
]

TRUTHS_GROUP = [
    "Who in this chat would you call first if you got arrested?",
    "Whose profile in this chat have you looked at most recently, and why?",
    "If your life were a movie, who in this chat would play the lead — and who'd be the villain?",
]

TRUTHS_DUO = [
    "What's one thing {subject} does that always makes you laugh?",
    "What's a memory with {subject} you think about more often than you'd admit?",
    "What's one habit of {subject}'s you'd steal for yourself?",
    "When was the last time {subject} genuinely surprised you?",
    "What were you doing the last time you thought 'I should text {subject}'?",
    "What did you think of {subject} the very first time you met?",
]

DARES = [
    "Send the last photo in your camera roll to this chat. No context allowed.",
    "Type your next three messages with your eyes closed. No fixing typos.",
    "Send a voice message singing the chorus of the last song you listened to.",
    "Change your profile picture to whatever the group picks for the next hour.",
    "DM {subject} just the words 'I know what you did' and screenshot their reply here.",
    "Send a selfie with your worst possible double chin.",
    "Write a haiku about the person who sent a message before you.",
    "Speak (type) only in rhymes for the next 10 minutes.",
    "Send your screen time report for this week.",
    "DM {subject} the single word 'soup' with zero context and report their reply to the chat.",
    "Reply to the next 5 messages with only GIFs.",
    "Send a voice message of your best evil laugh.",
    "Let the group write your Telegram bio for the next 24 hours.",
    "Share the most embarrassing photo of yourself you're willing to show.",
    "Type the alphabet backwards in one message. You get one attempt.",
    "Send a voice message reading the last text you sent, in a dramatic movie-trailer voice.",
    "Compliment every member of this chat, one message each.",
    "Do 10 push-ups right now and send a sweaty selfie as proof.",
    "Send a message to this chat in another language and refuse to translate it.",
    "Use only emojis to describe your day so far.",
    "Send the 14th photo in your camera roll. No explanations.",
    "Impersonate another member of this chat for the next 5 minutes.",
    "Send a voice message whispering 'I love cookies' as creepily as you can.",
    "Post your phone's battery percentage. If it's below 20%, take a second dare.",
    "Tell the group your most recent 'note to self' from your notes app.",
]

DARES_GROUP = []

DARES_DUO = [
    "Recreate {subject}'s profile picture as closely as you can and send your version.",
    "Let {subject} choose your profile picture for the next 24 hours.",
    "Do your best impression of {subject} in a voice message — they rate it out of 10.",
    "Send {subject} a compliment so sincere it becomes uncomfortable.",
    "Speak only in inside jokes for your next five messages; {subject} has to decode them.",
]

WOULD_YOU_RATHER = [
    "Would you rather always have to sing rather than speak, or dance everywhere you go?",
    "Would you rather be able to talk to animals or speak every human language?",
    "Would you rather fight one horse-sized duck or a hundred duck-sized horses?",
    "Would you rather lose the ability to read or lose the ability to speak?",
    "Would you rather always be 10 minutes late or always be 20 minutes early?",
    "Would you rather have unlimited money but no friends, or be broke with amazing friends?",
    "Would you rather know how you die or when you die?",
    "Would you rather have hiccups for the rest of your life or always feel like you have to sneeze?",
    "Would you rather be famous for something embarrassing or never be noticed at all?",
    "Would you rather live without music or live without movies?",
    "Would you rather have hands for feet or feet for hands?",
    "Would you rather teleport anywhere but arrive naked, or fly but only at walking speed?",
    "Would you rather never use social media again or never watch another series again?",
    "Would you rather eat only pizza for a year or never eat pizza again?",
    "Would you rather have your browser history public or your bank statement public?",
    "Would you rather be able to pause time or rewind time by 10 seconds?",
    "Would you rather sweat mayonnaise or cry hot sauce?",
    "Would you rather always say what you think or never be able to speak your mind?",
    "Would you rather live in a world without problems or rule a world full of them?",
    "Would you rather have a rewind button for your life or a mute button for other people?",
    "Would you rather be the funniest person in the room or the smartest?",
    "Would you rather give up cheese forever or give up chocolate forever?",
    "Would you rather your phone battery always be at 5% or your car/transport always be 5 minutes late?",
    "Would you rather wake up as a different person every day or be stuck as yourself with no sleep ever?",
    "Would you rather only whisper for the rest of your life or only shout?",
]

WOULD_YOU_RATHER_GROUP = []

WOULD_YOU_RATHER_DUO = [
    "Would you rather swap phones with {subject} for a day, or swap wardrobes for a week?",
    "Would you rather know exactly what {subject} really thinks of you, or have them know everything you think of them?",
    "Would you rather always have to text {subject} first, or never be allowed to text them first again?",
    "Would you rather team up with {subject} in every game forever, or always be on opposite sides?",
    "Would you rather only be able to talk to {subject} in memes, or only in extremely formal business English?",
]

# ------------------------------------------------------------ Spicy🌶️ pools
# Unlocked per chat with /spicymode on (admins only). These are ADDED to the
# regular pools, not a replacement. Flirty party-game territory, not explicit.

TRUTHS_SPICY = [
    "Rate {subject}'s flirting game out of 10, based on evidence from this chat.",
    "If {subject} asked you out completely seriously, what would you actually say?",
    "Say one thing about {subject} you find genuinely charming. No jokes allowed.",
]

TRUTHS_SPICY_GROUP = [
    "Who in this chat would you take on a date if you had to pick right now?",
    "Have you ever had even a two-minute crush on someone in this chat? Yes or no.",
    "If you had to marry one person in this chat, kiss another, and block a third — who's who?",
    "Whose profile picture in this chat have you looked at more than once? Be honest.",
    "What's the smoothest thing anyone in this chat has ever said, and who said it?",
    "Who in this chat would survive a first date with you, and who would run after ten minutes?",
    "Rank the top three huggers in this chat. Defend your podium.",
    "Who in this chat do you double-text without shame?",
    "Who in this chat is most likely to leave you on read — and who would you never leave on read?",
]

TRUTHS_SPICY_DUO = [
    "Have you ever had even a two-minute crush on {subject}? Answer fast — hesitation counts.",
    "What did you actually think the first time you saw {subject}'s profile picture?",
    "What's {subject}'s single most attractive quality? One answer.",
    "How many times a day do you check whether {subject} has texted?",
    "What's a message from {subject} you've reread more than once?",
    "Describe {subject} in exactly three words.",
    "What's the smoothest thing {subject} has ever said to you?",
]

DARES_SPICY = [
    "Send your best pickup line to this chat, addressed to {subject}, delivered completely seriously.",
    "Send a voice message saying 'hey you' to this chat as seductively as you can manage.",
    "Rate the profile picture of the person who messaged before you out of 10, with justification.",
    "DM {subject} 'thinking about you 👀' and screenshot their reply for the chat.",
    "Build the flirtiest emoji combo you can and dedicate it to a member of your choice.",
    "Wink at the camera and send the photo. No retakes.",
    "Serenade the chat: voice-message one verse of a love song to a member of your choice.",
    "Write a two-sentence romance novel opening starring two people in this chat.",
]

DARES_SPICY_GROUP = [
    "Describe your ideal date night with someone from this chat — the group has to guess who you pictured.",
    "Rank three members of this chat by 'most likely to break my heart'.",
]

DARES_SPICY_DUO = [
    "Describe your ideal date night with {subject}, start to finish. Vague answers don't count.",
    "Tell {subject} your favorite memory of the two of you, in full detail.",
    "Describe {subject}'s smile in one sentence. You have to actually send it.",
    "Send {subject} a voice message saying good night like you mean it.",
    "Plan your next hangout with {subject} right now, in this chat, and actually set a date.",
]

WOULD_YOU_RATHER_SPICY = [
    "Would you rather date someone from this chat or stay single for five years?",
    "Would you rather kiss {subject} or do every dare this chat can invent tonight?",
    "Would you rather hold hands with {subject} for an entire day, or never be allowed to sit next to them again?",
    "Would you rather slow dance with {subject} at a wedding, or give an unprepared toast about them?",
]

WOULD_YOU_RATHER_SPICY_GROUP = [
    "Would you rather all your DMs with people in this chat go public, or never be allowed to DM any of them again?",
    "Would you rather always have to make the first move on people in this chat, or never be allowed to?",
    "Would you rather see everyone's in-chat crushes revealed, or have yours revealed?",
    "Would you rather go on a blind date planned entirely by this chat, or plan one for {subject} yourself?",
]

WOULD_YOU_RATHER_SPICY_DUO = [
    "Would you rather re-live your first conversation with {subject}, or skip ahead five years to see where you two end up?",
    "Would you rather cook dinner for {subject} while they watch and comment, or have them cook for you and not be allowed to help?",
    "Would you rather {subject} see your entire camera roll, or your entire search history?",
    "Would you rather spend a whole day with {subject} in complete silence, or a whole day where neither of you is allowed to stop talking?",
]

# ------------------------------------------------------------------- roleplay

ROLEPLAY_ROLES = [
    "a paranoid conspiracy theorist",
    "an off-duty clown who refuses to admit it",
    "a retired secret agent trying to live a quiet life",
    "an influencer who livestreams everything",
    "a time traveler from 1875 hiding it badly",
    "a supervillain on their day off",
    "an overly enthusiastic tour guide",
    "a cat burglar mid-heist",
    "a royal in disguise as a commoner",
    "a robot pretending to be human, poorly",
    "a pirate captain who gets seasick",
    "a wizard who lost their wand and won't talk about it",
    "a detective who suspects everyone",
    "an alien anthropologist studying humans",
    "a celebrity chef who can't actually cook",
    "a ghost who doesn't know they're a ghost",
    "a startup founder pitching to literally anyone",
    "a medieval knight extremely confused by technology",
    "a soap-opera star who treats everything as a dramatic scene",
    "a lottery winner hiding it from everyone",
    "an undercover food critic",
    "a superhero whose only power is mild inconvenience",
    "a vampire trying to fit in at a day job",
    "a grandma who is secretly a hacker",
]

ROLEPLAY_SCENARIOS = [
    "You're all trapped in an elevator during a zombie outbreak.",
    "You're the crew of a spaceship and someone just ate the last snack.",
    "You're planning a heist on the world's most secure cookie factory.",
    "You've woken up at a wedding and none of you remember whose it is.",
    "You're the last people on Earth and must decide what to preserve.",
    "You're contestants on a cooking show and the oven just caught fire.",
    "You're a royal court and the king has just vanished mysteriously.",
    "You're stuck in an airport overnight and the wifi just went down.",
    "You're a band about to go on stage but your lead singer lost their voice.",
    "You're jurors deliberating the most ridiculous crime of the century.",
    "You're survivors on a desert island electing a leader.",
    "You're ghosts haunting the same house and arguing over territory.",
    "You're a group therapy session for retired superheroes.",
    "You're office coworkers and someone just microwaved fish. Again.",
    "You're medieval villagers and a dragon has applied to live nearby.",
    "You're on a road trip and the GPS has become sentient and opinionated.",
]

ROLEPLAY_SCENARIOS_DUO = [
    "You're two strangers who keep ending up in the same coffee shop at the same time. Today one of you finally says something.",
    "You're rival spies who just discovered you've been assigned to the same safehouse.",
    "You're the last two people at a party neither of you wanted to attend, waiting for the same taxi.",
    "You're co-hosts of a tiny 3am radio show and exactly one listener just called in.",
    "You're two knights guarding the same door for a king who left years ago.",
    "You're pen pals meeting in person for the first time after ten years of letters.",
]

# Spicy🌶️ roleplay: every entry is (scenario, daddy-energy role, babygirl-energy
# role). The two roles are shuffled between the first two players cast, so the
# dynamic is always in play but nobody's typecast. Suggestive, never explicit.
ROLEPLAY_SPICY_DYNAMICS = [
    ("Closing time at the bar one of you owns. The last customer has had "
     "exactly one drink and zero intention of leaving.",
     "the owner — daddy energy: flips chairs onto tables slowly, says "
     "“you're trouble” like a compliment",
     "the regular — babygirl energy: orders another drink they don't want, "
     "just to watch it get brought over"),
    ("A mob boss has to babysit the star witness in a safehouse overnight.",
     "the boss — dangerous everywhere else, patient here; “eat your "
     "dinner” is non-negotiable",
     "the witness — a flight risk in fuzzy socks, negotiating everything, "
     "winning nothing"),
    ("Private dance lesson, one week before the wedding you're both "
     "pretending this is about.",
     "the instructor — hands firm, counts slow, “again” means again",
     "the student — steps on toes on purpose, apologizes without meaning it"),
    ("A bodyguard and the celebrity who keeps sneaking out for 2am snacks.",
     "the bodyguard — catches every escape attempt and isn't mad, just "
     "disappointed; “careful” is a full sentence",
     "the celebrity — escapes strictly in order to be caught"),
    ("Road trip. The GPS died an hour ago and only one of you thinks that's "
     "a problem.",
     "the driver — one hand on the wheel, “we're not lost”, decides "
     "when snack stops happen",
     "the passenger — feet on the dash, asks “are we there yet” "
     "recreationally"),
    ("The CEO's coffee order has been wrong all week. Today the new hire "
     "brought the right one, plus an attitude.",
     "the CEO — expensive watch, low voice, “come here” from across "
     "the office",
     "the new hire — sweet smile, insubordinate on purpose, knows exactly "
     "which rules are being broken"),
    ("A pirate captain discovers a stowaway three days out to sea.",
     "the captain — should order them overboard, instead assigns the cabin "
     "next door; “stay where I can see you”",
     "the stowaway — zero remorse, negotiating dinner terms from inside a "
     "barrel"),
    ("The storm knocked the cabin's power out. One flashlight, one blanket, "
     "and an argument about who gets which.",
     "the one who built the fire — “come here, you're shivering” is "
     "a command, not an offer",
     "the one who “forgot” to pack warm clothes — cold on purpose"),
    ("A tattoo artist and the walk-in who cannot sit still.",
     "the artist — steady hands, “hold still, baby” in a voice that "
     "works",
     "the walk-in — flinches specifically to get held in place; picked a "
     "design that needs three sessions"),
    ("Poker night. One of you is losing on purpose. The other knows.",
     "the house — daddy energy: stacks chips slowly, raises stakes that "
     "aren't money",
     "the player — babygirl energy: all-in with a losing hand and a winning "
     "smile"),
]

# Secret phrases for /taboo: the describer must get the chat to guess the
# phrase without using ANY of its words, within 3 clue messages.
TABOO_PHRASES = [
    "I hate you",
    "I love you",
    "break a leg",
    "walk the dog",
    "happy birthday",
    "good morning sunshine",
    "call me later",
    "the early bird",
    "piece of cake",
    "spill the tea",
    "home sweet home",
    "money talks",
    "under the weather",
    "hit the road",
    "cold feet",
    "couch potato",
    "night owl",
    "third wheel",
    "food coma",
    "bad hair day",
    "monday morning",
    "netflix and chill",
    "read my mind",
    "out of office",
    "low battery",
    "seen but no reply",
    "group project",
    "free food",
    "awkward silence",
    "wrong number",
]

# {subject} is replaced with a random other member's name when possible.
PARANOIA_QUESTIONS = [
    "Who in this chat is most likely to become famous?",
    "Who in this chat would survive longest in a zombie apocalypse?",
    "Who in this chat is most likely to get arrested for something ridiculous?",
    "Who in this chat has the worst taste in music?",
    "Who in this chat would you least want to be stuck in an elevator with?",
    "Who in this chat is secretly the smartest?",
    "Who in this chat would win in a fist fight against everyone else?",
    "Who in this chat is most likely to cry at a movie?",
    "Who in this chat would you trust with your phone unlocked?",
    "Who in this chat is most likely to become a millionaire, then lose it all?",
    "Who in this chat texts the most unhinged things at 3am?",
    "Who in this chat is most likely to join a cult by accident?",
    "Do you think {subject} could keep a big secret?",
    "Would you lend {subject} money and expect it back?",
    "Is {subject} the type to snitch, yes or no?",
    "Would you let {subject} plan your birthday party?",
    "Do you think {subject} sings in the shower?",
    "Would you trust {subject} to drive you somewhere at 2am, no questions asked?",
    "Is {subject} more likely to become a CEO or a meme?",
    "Would you share a hotel room with {subject} for a week?",
    "Do you think {subject} has ever stalked someone's profile for over an hour?",
    "Would {subject} survive a week without their phone?",
]


# ------------------------------------------------------------ pool assembly

_POOLS = {
    "truth": (TRUTHS, TRUTHS_GROUP, TRUTHS_DUO,
              TRUTHS_SPICY, TRUTHS_SPICY_GROUP, TRUTHS_SPICY_DUO),
    "dare": (DARES, DARES_GROUP, DARES_DUO,
             DARES_SPICY, DARES_SPICY_GROUP, DARES_SPICY_DUO),
    "wyr": (WOULD_YOU_RATHER, WOULD_YOU_RATHER_GROUP, WOULD_YOU_RATHER_DUO,
            WOULD_YOU_RATHER_SPICY, WOULD_YOU_RATHER_SPICY_GROUP,
            WOULD_YOU_RATHER_SPICY_DUO),
}


def pool(category: str, *, duo: bool, spicy: bool) -> list[str]:
    """Assemble the prompt pool for a chat: any-size prompts plus either the
    group-only or the two-person variants, with spicy extras when enabled."""
    any_, grp, duo_l, s_any, s_grp, s_duo = _POOLS[category]
    out = any_ + (duo_l if duo else grp)
    if spicy:
        out = out + s_any + (s_duo if duo else s_grp)
    return out


# --------------------------------------------------------------------------
# Daily question ritual (/dailyq): an ordered arc inspired by Aron's "36
# questions" — starts light, gets steadily more personal and intimate. The
# index into this list is per-chat state, so each chat walks the arc once.

DAILY_QUESTIONS = [
    # Warm-up: easy, fun, zero risk
    "Given the choice of anyone in the world, whom would you want as a dinner guest?",
    "Would you like to be famous? In what way?",
    "Before making a phone call, do you ever rehearse what you're going to say? Why?",
    "What would constitute a perfect day for you?",
    "When did you last sing to yourself? To someone else?",
    "If you could wake up tomorrow having gained one quality or ability, what would it be?",
    "What's a small thing that instantly improves your day?",
    "What's the most spontaneous thing you've ever done?",
    "If you could live anywhere in the world for one year, where and why?",
    "What's something you're weirdly good at?",
    "What did you want to be when you were 10, and what happened to that dream?",
    "For what in your life do you feel most grateful right now?",
    # Getting personal: values, history, self-image
    "If you could change anything about the way you were raised, what would it be?",
    "Take four minutes and tell your life story in as much detail as possible.",
    "If a crystal ball could tell you the truth about yourself, your life, or the future, what would you want to know?",
    "Is there something you've dreamed of doing for a long time? Why haven't you done it?",
    "What is the greatest accomplishment of your life so far?",
    "What do you value most in a friendship?",
    "What is your most treasured memory?",
    "What is your most terrible memory?",
    "If you knew that in one year you'd die suddenly, would you change anything about the way you're living? Why?",
    "What does friendship — real friendship — mean to you?",
    "What roles do love and affection play in your life?",
    "How close and warm was your family growing up? Do you feel your childhood was happier than most people's?",
    # Closer: about the two of you
    "Name three things you and I appear to have in common.",
    "What's something you've always wanted to ask me but haven't?",
    "Share five things you honestly like about me.",
    "What's your first memory of me?",
    "What was your first impression of me, and how wrong was it?",
    "If we were going to become closer than we are, what would you want me to know about you?",
    "Tell me something you've never told anyone — or almost no one.",
    "What, if anything, is too serious to be joked about?",
    "When did you last cry in front of another person? By yourself?",
    "What's something about me you're jealous of?",
    "If you were to die this evening with no chance to talk to anyone, what would you most regret not having told someone? Why haven't you told them yet?",
    "Of all the people in your life, whose death would you find most disturbing? (Yes, you have to answer.)",
    # Deep end: vulnerability, us, the future
    "Complete this sentence: 'I wish I had someone with whom I could share…'",
    "What's one thing about yourself you're still learning to accept?",
    "When do you feel most like yourself around me?",
    "What's a moment between us you think about more than you've admitted?",
    "What do you think we'll be doing in ten years?",
    "What's the hardest thing you've ever forgiven someone for?",
    "What's one way I've changed you?",
    "If tonight was our last conversation ever, what would you want to say?",
    "What are you most afraid of in relationships — and where did that come from?",
    "What's something you want us to do together that we keep not doing?",
    "Describe the last time you felt truly, stupidly happy.",
    "What's one thing you hope never changes between us?",
]

# Appended to the arc when /spicymode is on for the chat: same escalation
# philosophy — suggestive, adults-only, about the people in this chat.
DAILY_QUESTIONS_SPICY = [
    "What were you actually thinking the first time you found me attractive?",
    "What's the most attractive non-physical thing about me?",
    "Describe your idea of a perfect kiss. Be specific.",
    "What's something flirty you almost sent me but deleted?",
    "Where do you like to be touched that nobody's ever asked about?",
    "What outfit of mine do you think about?",
    "What's a fantasy you've never said out loud?",
    "What's the boldest thing you've ever wanted to do with me but haven't dared?",
    "Voice message: say the thing you'd whisper if we were alone right now.",
    "What's something new you want to try — that involves me?",
    "Describe the moment you were most attracted to me. What did I do?",
    "If we had 24 hours together with zero obligations and zero judgment, walk me through the itinerary.",
    "What's a compliment about your body you secretly wish someone would give you?",
    "What song would you want playing? You know for when.",
    "What's your favorite memory of us that you'd never tell anyone else about?",
    "Truth: have you ever dreamed about me? Details required.",
]
