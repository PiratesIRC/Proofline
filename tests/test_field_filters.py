import pytest

from proofline.field_filters import (
    ADDRESS_BAR_CLASS_MARKERS,
    SENSITIVE_PATTERN,
    FieldTraits,
    skip_reason,
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
        "Email or Mobile Number",
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
