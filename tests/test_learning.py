from hushtype.learning import candidate_names, extract_corrections


def test_learns_misspelled_name():
    assert extract_corrections("Thanks Sara for the update", "Thanks Sarah for the update") == [("sara", "Sarah")]


def test_learns_misheard_acronym():
    assert extract_corrections("We use eye tools daily", "We use AI tools daily") == [("eye", "AI")]


def test_learns_capitalisation_of_names():
    assert extract_corrections("meeting with khurram today", "meeting with Khurram today") == [("khurram", "Khurram")]


def test_ignores_rewording():
    assert extract_corrections("This is a good post", "This is a great post") == []
    assert extract_corrections("Send it to the team", "Send it to a team") == []
    assert extract_corrections("I think so", "I believe so") == []


def test_ignores_added_or_removed_text():
    assert extract_corrections("Thanks", "Thanks a lot, Sarah") == []


def test_urdu_fix_is_learned():
    old = "کل کی میٹنگ تین بجے رکھ لیتے ہیں"
    new = "کل کی میٹنگ تین بجے رکھ لیتے ہیں"
    assert extract_corrections(old, new) == []
    assert extract_corrections("فیلپائنی فوٹوگرافر", "فلپائنی فوٹوگرافر") == [("فیلپائنی", "فلپائنی")]


def test_candidate_names_skip_sentence_starts():
    text = "Great post. I met Sarah at LinkedIn in Vienna. Thanks"
    assert candidate_names(text) == ["Sarah", "LinkedIn", "Vienna"]
