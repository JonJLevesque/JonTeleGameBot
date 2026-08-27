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

# Truths are always about the OTHER person ({subject}: a random other member
# in groups, the partner in duo chats) — never a solo self-inventory question.
# A few subjectless-but-other-directed ones remain for cold starts where the
# bot doesn't know any other members yet.
TRUTHS = [
    "What's one opinion of {subject}'s that you secretly disagree with?",
    "What's something {subject} does better than they realize?",
    "When was the last time {subject} hurt your feelings without knowing it?",
    "What do you envy about {subject}? Real answer.",
    "What's a conversation you keep meaning to have with {subject} but haven't?",
    "What's the closest you and {subject} ever came to actually falling out?",
    "What's something you've never properly thanked {subject} for?",
    "What part of {subject}'s life do you secretly wish you had?",
    "What's a side of {subject} you think nobody else gets to see?",
    "When were you most proud of {subject}? Be specific.",
    "What's one thing {subject} believes about you that isn't true?",
    "If {subject} could hear one hard truth from you with zero consequences, what would it be?",
    "What's the most {subject} thing {subject} has ever done?",
    "When did {subject} change your mind about something that mattered?",
    "What worry do you have about {subject} that you've never said out loud?",
    "What's a moment {subject} showed up for you that you still think about?",
    "If you and {subject} ever stopped talking, what would you miss first?",
    "What's something {subject} said ages ago that you still think about?",
    "What advice would you give {subject} if you knew they couldn't get offended?",
    "If you had one wish to spend on {subject}'s life, what would you fix or give them?",
    "How has {subject} changed since you first met them?",
    "Which of {subject}'s habits have you caught yourself copying?",
    "What's the hardest thing you've ever had to tell someone you love?",
    "Who in your life do you owe an apology to, and for what?",
    "Who was your last 3am 'I need to talk' call, and what was it about?",
    "What's the nicest thing anyone in this chat has done for you?",
    "Who was the last person you couldn't stop thinking about, and why?",
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
    "What's something about {subject} you hope never changes?",
    "What's one thing you've never told {subject} because the moment never felt right? The moment is now.",
    "When was the last time {subject} made you feel genuinely seen?",
    "What do you and {subject} both pretend not to notice about each other?",
    "If {subject} moved across the world tomorrow, what would you say tonight?",
    "What's a small thing {subject} did that permanently changed how you saw them?",
    "Which of {subject}'s flaws have you fully made peace with — and which one still gets you?",
    "What has {subject} taught you about yourself?",
    "What's the biggest thing you've done for {subject} that they still don't know about?",
    "When do you feel closest to {subject}?",
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
    "Would you rather have to end every sentence with 'in theory' or start every sentence with 'listen…'?",
    "Would you rather get every song stuck in your head for exactly one week, or never have a song stuck in your head again — including the ones you love?",
    "Would you rather your alarm sound be your own voice saying 'wake up bestie' or a recording of your most embarrassing moment?",
    "Would you rather always order the wrong thing at restaurants but enjoy it, or always order the right thing and be slightly disappointed?",
    "Would you rather lose all your saved passwords once a month, or have autocorrect change one word per message and never know which?",
    "Would you rather be brutally honest in every compliment you give, or never be able to give compliments at all?",
    "Would you rather relive your best day once a year (it uses up a normal day), or get one extra ordinary day every year?",
    "Would you rather every stranger remember your name forever, or remember every stranger's name but they never remember yours?",
    "Would you rather apologize first every single time, or win every argument but sleep on the couch?",
    "Would you rather your pet (real or future) could talk but was extremely judgmental, or stay silent but post about you online?",
    "Would you rather have to sing your side of every argument, or have every argument transcribed and mailed to your parents?",
    "Would you rather permanently lose one hour of sleep a night, or once a month sleep through something genuinely important?",
]

WOULD_YOU_RATHER_GROUP = []

WOULD_YOU_RATHER_DUO = [
    "Would you rather swap phones with {subject} for a day, or swap wardrobes for a week?",
    "Would you rather know exactly what {subject} really thinks of you, or have them know everything you think of them?",
    "Would you rather always have to text {subject} first, or never be allowed to text them first again?",
    "Would you rather team up with {subject} in every game forever, or always be on opposite sides?",
    "Would you rather only be able to talk to {subject} in memes, or only in extremely formal business English?",
    "Would you rather {subject} could read your search history, or your saved posts and screenshots?",
    "Would you rather win every argument with {subject} but they secretly keep score, or lose every one but they think you're a saint?",
    "Would you rather {subject} always pick the restaurant, or always pick the movie — forever, no vetoes?",
    "Would you rather get a notification every time {subject} thinks about you, or have them get one every time you think about them?",
    "Would you rather do {subject}'s laundry for a year, or let them set your profile picture for a year?",
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
    "What was {subject} wearing the last time you couldn't stop staring? Be exact.",
    "What's one thing {subject} does — that they don't know they do — that drives you a little crazy?",
    "When was the last time you wanted to kiss {subject} and didn't? What stopped you?",
    "Describe the last dream you had about {subject} that you never mentioned.",
    "What's something you want {subject} to do more often? Say it plainly — hints don't count.",
    "What do you think about when {subject} takes too long to text back at night?",
    "What's the most attractive thing {subject} did this month — and did they know they were doing it?",
    "What's one thing you've always wanted to hear {subject} say out loud?",
    "Which was better: your first kiss with {subject} or your most recent one? Defend your answer.",
    "What's a moment with {subject} you replay when you're alone?",
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
    "Voice message, slow and quiet: say {subject}'s name and nothing else.",
    "Type out what you'd whisper to {subject} at 1am if they were right next to you. Send it.",
    "Give {subject} three commands for tonight. They get to pick exactly one to obey.",
    "Describe your next kiss with {subject} — in advance, in detail. Congratulations, it's now a promise.",
    "Tell {subject} the unedited version of what you thought the last time they got dressed up.",
    "Send the compliment you've been sitting on because it felt like too much. Now.",
    "Send a photo of the spot where you wish {subject} was right now.",
    "Voice message: say 'come here' like you only get one take.",
    "Tell {subject} exactly where you'd want their attention tonight, in one sentence, no emoji to hide behind.",
    "Set a timer for tonight, tell {subject} what happens when it goes off, and mean it.",
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
    "Would you rather {subject} see your entire camera roll, or your entire search history?",
    "Would you rather a whole evening with {subject} where you can only communicate by touch, or one where you can't touch at all?",
    "Would you rather tell {subject} your most embarrassing fantasy, or have them invent one for you and be required to hear it read aloud?",
    "Would you rather {subject} describe exactly what they find attractive about you to your face for two full minutes, or never get to hear it?",
    "Would you rather always have to say what you're really thinking when {subject} catches you staring, or lose staring privileges for a month?",
    "Would you rather {subject} pick your next date night with no veto, or plan it yourself but they read your search history from the planning?",
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
    # idioms & classics
    "break the ice",
    "spill the beans",
    "hit the sack",
    "once in a blue moon",
    "better late than never",
    "beat around the bush",
    "bite the bullet",
    "cry over spilled milk",
    "curiosity killed the cat",
    "hit the nail on the head",
    "let the cat out of the bag",
    "on thin ice",
    "raining cats and dogs",
    "the last straw",
    "through thick and thin",
    "time flies",
    "up in the air",
    "when pigs fly",
    "wild goose chase",
    "you snooze you lose",
    "a blessing in disguise",
    "back to square one",
    "barking up the wrong tree",
    "birds of a feather",
    "burn the midnight oil",
    "butterflies in my stomach",
    "call it a day",
    "cutting corners",
    "devil's advocate",
    "don't push your luck",
    "down to earth",
    "elephant in the room",
    "fish out of water",
    "go the extra mile",
    "hang in there",
    "in hot water",
    "it takes two to tango",
    "jump on the bandwagon",
    "kill two birds",
    "love at first sight",
    "long story short",
    "miss the boat",
    "needle in a haystack",
    "no pain no gain",
    "off the hook",
    "on cloud nine",
    "out of the blue",
    "over the moon",
    "plot twist",
    "rain check",
    "saved by the bell",
    "sleep on it",
    "slow and steady",
    "speak of the devil",
    "steal my thunder",
    "take it easy",
    "the icing on the cake",
    "tie the knot",
    "tip of the iceberg",
    "twist my arm",
    "walk on eggshells",
    "whatever floats your boat",
    "your guess is as good as mine",
    "actions speak louder than words",
    "second wind",
    "sit tight",
    "under pressure",
    "easy does it",
    "cost an arm and a leg",
    # phones & internet
    "left on read",
    "do not disturb",
    "screenshot this",
    "main character energy",
    "touch grass",
    "living rent free",
    "ghosted again",
    "sliding into dms",
    "doom scrolling",
    "airplane mode",
    "wrong group chat",
    "going viral",
    "hot take",
    "humble brag",
    "photo dump",
    "soft launch",
    "situationship",
    "red flag",
    "green flag",
    "love language",
    "friend zone",
    "spoiler alert",
    "binge watching",
    "cliffhanger ending",
    "autocorrect fail",
    "voice message",
    "delete for everyone",
    "mute the group",
    "pin the message",
    "story time",
    "vibe check",
    "side quest",
    "glow up",
    "battery at one percent",
    "typing three dots",
    "blue checkmark",
    "cancel culture",
    "toxic ex",
    # everyday & couple-y
    "midnight snack",
    "morning coffee",
    "lazy sunday",
    "date night",
    "road trip playlist",
    "stolen fries",
    "big spoon",
    "little spoon",
    "forehead kiss",
    "matching pajamas",
    "inside joke",
    "first date jitters",
    "meet the parents",
    "anniversary dinner",
    "breakfast in bed",
    "movie marathon",
    "shared blanket",
    "cold pizza",
    "grocery run",
    "laundry day",
    "snooze button",
    "bad wifi",
    "dead battery",
    "lost keys",
    "traffic jam",
    "awkward hug",
    "power nap",
    "sweet tooth",
    "comfort food",
    "guilty pleasure",
    "retail therapy",
    "window shopping",
    "people watching",
    "small talk",
    "eye contact",
    "slow dance",
    "love letter",
    "pinky promise",
    "bear hug",
    "goodnight text",
    "late night talks",
    "long distance",
    "honeymoon phase",
    "brain freeze",
    "food baby",
    "hangry mood",
    "secret recipe",
    "extra cheese",
    "sweet and sour",
    "midnight munchies",
    "coffee addict",
    "happy tears",
    "ugly crying",
    "victory lap",
    "beginner's luck",
    "sore loser",
    "poker face",
    "game night",
    "trust fall",
    "staring contest",
    "silent treatment",
    "puppy eyes",
    "bed head",
    "morning person",
    "five more minutes",
    "socks and sandals",
    "dad joke",
    "mom voice",
    "new year new me",
    "shower singer",
    "car karaoke",
    "overthinking it",
    "famous last words",
]

# Extra phrases mixed in when Spicy🌶️ mode is on: flirty, never explicit.
TABOO_PHRASES_SPICY = [
    "pillow talk",
    "bedroom eyes",
    "love bite",
    "skinny dipping",
    "strip poker",
    "cold shower",
    "birthday suit",
    "seven minutes in heaven",
    "morning voice",
    "neck kisses",
    "home alone tonight",
    "slow burn",
    "friends with benefits",
    "sneaky link",
    "making out",
    "back scratches",
    "bite my lip",
    "dirty talk",
    "body heat",
    "lingerie shopping",
    "morning after",
    "playing hard to get",
    "love drunk",
    "weak in the knees",
]

# ------------------------------------------------------------------- trivia
# Static bank for /trivia when the AI is unavailable. Each entry is
# (question, correct_answer, [three wrong answers]) — the handler shuffles
# the options before posting, so the correct answer's position here is fine.

TRIVIA = [
    ("Which planet in our solar system has the most confirmed moons?",
     "Saturn", ["Jupiter", "Neptune", "Uranus"]),
    ("What is the only metal that is liquid at room temperature?",
     "Mercury", ["Gallium", "Sodium", "Tin"]),
    ("In which country was the tea bag invented?",
     "United States", ["England", "China", "India"]),
    ("What is the largest organ of the human body?",
     "The skin", ["The liver", "The lungs", "The brain"]),
    ("Which ocean is the deepest?",
     "Pacific", ["Atlantic", "Indian", "Arctic"]),
    ("How many hearts does an octopus have?",
     "Three", ["One", "Two", "Four"]),
    ("Which was Disney's first feature-length animated film?",
     "Snow White and the Seven Dwarfs", ["Pinocchio", "Fantasia", "Bambi"]),
    ("Which element has the chemical symbol Au?",
     "Gold", ["Silver", "Aluminium", "Copper"]),
    ("The Great Barrier Reef lies off the coast of which country?",
     "Australia", ["Brazil", "Indonesia", "Mexico"]),
    ("Who painted 'The Starry Night'?",
     "Vincent van Gogh", ["Claude Monet", "Pablo Picasso", "Salvador Dalí"]),
    ("What is the capital of Canada?",
     "Ottawa", ["Toronto", "Vancouver", "Montreal"]),
    ("Which language has the most native speakers worldwide?",
     "Mandarin Chinese", ["English", "Spanish", "Hindi"]),
    ("In what year did the Berlin Wall fall?",
     "1989", ["1991", "1987", "1993"]),
    ("Which animal's fingerprints are so like ours they've confused crime scenes?",
     "Koala", ["Chimpanzee", "Raccoon", "Gorilla"]),
    ("What is the smallest country in the world?",
     "Vatican City", ["Monaco", "San Marino", "Liechtenstein"]),
    ("Which planet is the hottest in our solar system?",
     "Venus", ["Mercury", "Mars", "Jupiter"]),
    ("How many bones does an adult human body have?",
     "206", ["186", "226", "300"]),
    ("Which fruit wears its seeds on the outside?",
     "Strawberry", ["Raspberry", "Fig", "Pomegranate"]),
    ("Who wrote 'Pride and Prejudice'?",
     "Jane Austen", ["Charlotte Brontë", "Mary Shelley", "Emily Dickinson"]),
    ("Which country has the most time zones, territories included?",
     "France", ["Russia", "United States", "China"]),
    ("What is a group of crows called?",
     "A murder", ["A conspiracy", "A gaggle", "A parliament"]),
    ("Mount Everest sits on the border of Nepal and which other country?",
     "China", ["India", "Bhutan", "Pakistan"]),
    ("In Morse code, which letter is a single dot?",
     "E", ["T", "A", "I"]),
    ("Which chess piece can only ever move diagonally?",
     "Bishop", ["Rook", "Knight", "Queen"]),
    ("What is the national animal of Scotland?",
     "The unicorn", ["The stag", "The lion", "The golden eagle"]),
    ("Which company was originally called 'BackRub'?",
     "Google", ["Amazon", "Yahoo", "Facebook"]),
    ("How long is a marathon, to the nearest kilometre?",
     "42 km", ["38 km", "45 km", "50 km"]),
    ("Which vitamin does your body produce when sunlight hits your skin?",
     "Vitamin D", ["Vitamin C", "Vitamin A", "Vitamin B12"]),
    ("What is the longest river entirely within Europe?",
     "The Volga", ["The Danube", "The Rhine", "The Loire"]),
    ("How many keys does a standard piano have?",
     "88", ["76", "92", "100"]),
    ("Which country gifted the Statue of Liberty to the United States?",
     "France", ["England", "Spain", "Italy"]),
    ("What is the rarest naturally occurring blood type?",
     "AB negative", ["O negative", "B negative", "A positive"]),
    ("Which planet spins on its side, rolling around the Sun like a barrel?",
     "Uranus", ["Neptune", "Saturn", "Pluto"]),
    ("The Mona Lisa hangs in which museum?",
     "The Louvre", ["The Uffizi", "The Prado", "The Met"]),
    ("What is the fastest land animal?",
     "Cheetah", ["Pronghorn", "Greyhound", "Lion"]),
    ("What colour is a polar bear's skin under all that fur?",
     "Black", ["Pink", "White", "Grey"]),
    ("How many strings does a standard violin have?",
     "Four", ["Five", "Six", "Three"]),
    ("Which is the only continent with no native snakes?",
     "Antarctica", ["Australia", "Europe", "South America"]),
    ("In what year did the Titanic sink?",
     "1912", ["1905", "1918", "1921"]),
    ("Who was the first woman to win a Nobel Prize?",
     "Marie Curie", ["Rosalind Franklin", "Florence Nightingale", "Ada Lovelace"]),
    ("Which gas makes up about 78% of Earth's atmosphere?",
     "Nitrogen", ["Oxygen", "Carbon dioxide", "Argon"]),
    ("What is the hardest naturally occurring substance on Earth?",
     "Diamond", ["Quartz", "Titanium", "Obsidian"]),
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
