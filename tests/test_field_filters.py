import pytest

from proofline.field_filters import (
    ADDRESS_BAR_CLASS_MARKERS,
    SENSITIVE_PATTERN,
    FieldTraits,
    skip_reason,
    text_skip_reason,
)


def traits(**overrides: object) -> FieldTraits:
    defaults: dict[str, object] = {
        "control_type": "EditControl",
        "class_name": "",
        "name": "",
        "help_text": "",
        "automation_id": "",
        "has_range_value": False,
    }
    defaults.update(overrides)
    return FieldTraits(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "class_name",
    ["UrlBar-UrlField", "OmniboxViewViews", "urlbar-input"],
)
def test_address_bar_class_names_are_skipped(class_name):
    assert skip_reason(traits(class_name=class_name)) == "address bar"


def test_address_bar_markers_are_all_detected():
    for marker in ADDRESS_BAR_CLASS_MARKERS:
        assert skip_reason(traits(class_name=marker)) == "address bar"


def test_address_bar_automation_id_is_skipped():
    assert skip_reason(traits(automation_id="urlbar-input")) == "address bar"


def test_address_bar_class_match_is_case_insensitive():
    assert skip_reason(traits(class_name="omniboxviewviews")) == "address bar"


@pytest.mark.parametrize(
    "overrides",
    [
        {"has_range_value": True},
        {"control_type": "SpinnerControl"},
    ],
)
def test_numeric_fields_are_skipped(overrides):
    assert skip_reason(traits(**overrides)) == "numeric field"


@pytest.mark.parametrize(
    ("overrides", "phrase"),
    [
        ({"name": "Password"}, "password"),
        ({"name": "Enter your passcode"}, "passcode"),
        ({"name": "Passphrase"}, "passphrase"),
        ({"name": "One-time code"}, "one-time code"),
        ({"name": "one time code"}, "one time code"),
        ({"name": "OTP"}, "otp"),
        ({"name": "Verification code"}, "verification code"),
        ({"name": "Security code"}, "security code"),
        ({"name": "Authentication code"}, "authentication code"),
        ({"name": "Auth code"}, "auth code"),
        ({"name": "2FA code"}, "2fa code"),
        ({"name": "MFA"}, "mfa"),
        ({"name": "PIN"}, "pin"),
        ({"name": "CVV"}, "cvv"),
        ({"name": "CVC"}, "cvc"),
        ({"name": "Card number"}, "card number"),
        ({"name": "Credit card"}, "credit card"),
        ({"name": "Debit card"}, "debit card"),
        ({"name": "Card no"}, "card no"),
        ({"name": "Expiry date"}, "expiry date"),
        ({"name": "Expiration date"}, "expiration date"),
        ({"name": "Routing number"}, "routing number"),
        ({"name": "Account number"}, "account number"),
        ({"name": "IBAN"}, "iban"),
        ({"name": "SSN"}, "ssn"),
        ({"name": "Social security"}, "social security"),
        ({"name": "Tax ID"}, "tax id"),
        ({"name": "API key"}, "api key"),
        ({"name": "Access key"}, "access key"),
        ({"name": "Secret key"}, "secret key"),
        ({"name": "Client secret"}, "client secret"),
        ({"name": "Token"}, "token"),
    ],
)
def test_sensitive_labels_are_skipped(overrides, phrase):
    assert skip_reason(traits(**overrides)) == f"sensitive field ({phrase})"


@pytest.mark.parametrize(
    ("overrides", "phrase"),
    [
        ({"help_text": "Enter your password"}, "password"),
        ({"help_text": "6-digit verification code"}, "verification code"),
        ({"automation_id": "cc-number"}, "cc-number"),
        ({"automation_id": "cc-csc"}, "cc-csc"),
        ({"automation_id": "cc-exp"}, "cc-exp"),
        ({"automation_id": "cc-exp-month"}, "cc-exp"),
        ({"automation_id": "card_number"}, "card_number"),
    ],
)
def test_sensitive_matches_via_help_text_and_automation_id(overrides, phrase):
    assert skip_reason(traits(**overrides)) == f"sensitive field ({phrase})"


@pytest.mark.parametrize(
    "name",
    ["PASSWORD", "password", "PaSsWoRd", "CARD NUMBER", "Api Key"],
)
def test_sensitive_match_is_case_insensitive(name):
    assert skip_reason(traits(name=name)).startswith("sensitive field (")


def test_reason_phrase_is_lower_cased():
    assert skip_reason(traits(name="CARD NUMBER")) == "sensitive field (card number)"


@pytest.mark.parametrize(
    "name",
    [
        "Message",
        "Subject",
        "Comments",
        "Description",
        "Notes",
        "Write a reply",
        "Email body",
        "Opinion",
        "Shopping list",
        "Spinning class notes",
        "Pinned notes",
        "tokenize this",
        "Email message",
        "E-mail text",
        "Mobile Number notes",
    ],
)
def test_ordinary_labels_are_not_flagged(name):
    assert skip_reason(traits(name=name)) == ""


def test_ordinary_help_text_and_automation_id_are_not_flagged():
    assert skip_reason(traits(help_text="Write a reply", automation_id="msgBody")) == ""


def test_neutral_field_is_allowed():
    assert skip_reason(traits()) == ""


def test_address_bar_takes_precedence_over_sensitive_label():
    assert skip_reason(traits(class_name="OmniboxViewViews", name="Password")) == "address bar"


def test_numeric_takes_precedence_over_sensitive_label():
    assert skip_reason(traits(has_range_value=True, name="PIN")) == "numeric field"


def test_sensitive_pattern_is_exported_and_compiled():
    assert SENSITIVE_PATTERN.search("Enter PIN")
    assert SENSITIVE_PATTERN.search("spinning") is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "Search"},
        {"name": "Search box"},  # Start menu (SearchHost.exe)
        {"name": "Search box, Find a setting"},  # Windows Settings
        {"name": "Search recordings..."},  # a web app placeholder
        {"help_text": "Type to search"},
        {"localized_control_type": "search box"},  # <input type=search> in Chromium and Firefox
        {"automation_id": "SearchEditBox"},
        {"automation_id": "txtSearch"},
        {"automation_id": "site-search"},
        {"class_name": "SearchTextBox"},
    ],
)
def test_search_fields_are_skipped(overrides):
    assert skip_reason(traits(**overrides)) == "search field"


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "Research notes"},
        {"automation_id": "researchNotes"},
        {"class_name": "Researcher"},
        {"localized_control_type": "edit"},
    ],
)
def test_words_containing_search_are_not_search_fields(overrides):
    assert skip_reason(traits(**overrides)) == ""


def test_address_bar_wins_over_search():
    assert skip_reason(traits(class_name="OmniboxViewViews", name="Address and search bar")) == "address bar"


# The cases below are fields measured in a user's log on 2026-11-03 that were checked but
# should not have been.


@pytest.mark.parametrize(
    "overrides",
    [
        {"class_name": "REComboBox20W", "name": "Click Snooze to be reminded in:"},  # Outlook reminders
        {"control_type": "ComboBoxControl", "class_name": "ms-TextField-field field-1773", "name": "Date"},
        {"control_type": "ComboBoxControl", "class_name": "chakra-combobox__input", "name": "Folder"},
    ],
)
def test_dropdowns_are_skipped(overrides):
    assert skip_reason(traits(**overrides)) == "dropdown (combo box)"


@pytest.mark.parametrize(
    ("overrides", "phrase"),
    [
        ({"name": "User name"}, "user name"),
        ({"name": "username"}, "username"),
        ({"name": "Username"}, "username"),
        ({"name": "Enter your email address"}, "email"),
        ({"name": "Email address *"}, "email"),
        ({"name": "Enter your email, phone, or Skype."}, "email"),
        ({"name": "Add another email address"}, "email"),
        ({"name": "LogMeIn ID:", "class_name": "form-control inset ls-spr email"}, "email"),
        ({"class_name": "form-control form-control-email svelte-o"}, "email"),
        ({"automation_id": "loginId"}, "loginid"),
        ({"name": "E-mail"}, "e-mail"),
        ({"name": "Email or Mobile Number"}, "email"),  # a sign-in label; "Mobile Number" is not sensitive
    ],
)
def test_user_name_and_email_fields_are_skipped(overrides, phrase):
    assert skip_reason(traits(**overrides)) == f"account field ({phrase})"


@pytest.mark.parametrize(
    "name",
    ["Your name", "Display name", "Name of the item", "Emailing tips", "Users", "Project Lead Name"],
)
def test_names_that_are_not_sign_in_fields_are_checked(name):
    assert skip_reason(traits(name=name)) == ""


@pytest.mark.parametrize(
    ("name", "phrase"),
    [
        ("Enter code", "enter code"),
        ("Secure Code", "secure code"),
        ("Enter time-based code", "time-based code"),
    ],
)
def test_code_entry_fields_are_skipped(name, phrase):
    assert skip_reason(traits(name=name)) == f"sensitive field ({phrase})"


@pytest.mark.parametrize(
    "name",
    [
        "RE: Password changes for the shared drive - Message",  # an Outlook reply, named after its subject
        "Search results for the audit",
        "Your email still goes to the old address",
    ],
)
def test_document_names_are_not_field_labels(name):
    assert skip_reason(traits(control_type="DocumentControl", class_name="_WwG", name=name)) == ""


def test_document_controls_still_skip_numeric_and_address_bar_rules():
    assert skip_reason(traits(control_type="DocumentControl", has_range_value=True)) == "numeric field"


@pytest.mark.parametrize(
    "text",
    ["127.0.0.1", "$142.00", "755.26", "10/31/2026", "(555) 555-0100", "  42  ", "1."],
)
def test_text_of_only_numbers_is_skipped(text):
    assert text_skip_reason(text) == "numeric field (numbers only)"


@pytest.mark.parametrize(
    "text",
    ["", "   ", "Room 42", "B14", "...", "Thanks for reaching out", "1. Order the parts"],
)
def test_text_with_letters_or_no_digits_is_checked(text):
    assert text_skip_reason(text) == ""


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"automation_id": "password-box"}, "sensitive field (password)"),
        ({"help_text": "Enter your PIN"}, "sensitive field (pin)"),
        ({"automation_id": "txtSearch"}, "search field"),
        ({"class_name": "username-doc"}, "account field (username)"),
    ],
)
def test_document_controls_still_use_help_text_id_and_class(overrides, reason):
    assert skip_reason(traits(control_type="DocumentControl", name="Ordinary title", **overrides)) == reason


@pytest.mark.parametrize(
    ("automation_id", "phrase"),
    [
        ("txtPassword", "password"),
        ("userPassword", "password"),
        ("loginPassword", "password"),
        ("creditCardNumber", "credit card"),
        ("myApiKey", "api key"),
        ("userPin", "pin"),
        ("APIKey", "apikey"),
        ("txtTokenId", "token"),
    ],
)
def test_camel_case_ids_with_a_sensitive_word_are_skipped(automation_id, phrase):
    assert skip_reason(traits(automation_id=automation_id)) == f"sensitive field ({phrase})"


@pytest.mark.parametrize("automation_id", ["msgBody", "spinnerText", "pinnedNote", "tokenizeInput", "txtDescription"])
def test_camel_case_ids_without_a_sensitive_word_are_checked(automation_id):
    assert skip_reason(traits(automation_id=automation_id)) == ""


@pytest.mark.parametrize(("overrides", "phrase"), [
    ({"automation_id": "txtUserName"}, "user name"),
    ({"class_name": "loginEmail"}, "email"),
])
def test_camel_case_ids_of_sign_in_fields_are_skipped(overrides, phrase):
    assert skip_reason(traits(**overrides)) == f"account field ({phrase})"


@pytest.mark.parametrize(("automation_id", "phrase"), [
    ("passWord", "password"),
    ("PassCode", "passcode"),
    ("txtPassPhrase", "pass phrase"),
    ("SignInCode", "signincode"),
])
def test_ids_that_split_inside_a_sensitive_word_are_still_skipped(automation_id, phrase):
    assert skip_reason(traits(automation_id=automation_id)) == f"sensitive field ({phrase})"


def test_class_names_that_split_inside_a_sign_in_word_are_still_skipped():
    assert skip_reason(traits(class_name="UserName")).startswith("account field (")
