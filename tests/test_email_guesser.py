"""Tests for LLM email guessing metadata."""

from unittest.mock import MagicMock, patch

from openrole.agents.email_guesser import guess_emails_with_llm
from openrole.schemas.contact import DiscoveredContact


def test_guess_emails_tags_ai_generated():
    contact = DiscoveredContact(
        full_name="Matthias Rivollier",
        title="Safeguards Data Scientist",
    )
    fake_response = MagicMock()
    fake_response.content = """{
      "emails": [
        {
          "full_name": "Matthias Rivollier",
          "email": "matthias@anthropic.com",
          "confidence": 78,
          "pattern": "first@domain"
        }
      ]
    }"""

    with patch("openrole.agents.email_guesser.get_settings") as gs:
        gs.return_value.llm_configured = True
        with patch("openrole.agents.email_guesser.get_chat_model") as gcm:
            gcm.return_value.invoke.return_value = fake_response
            result, warnings = guess_emails_with_llm(
                [contact],
                company_name="Anthropic",
                company_domain="anthropic.com",
            )

    assert result[0].email == "matthias@anthropic.com"
    assert result[0].metadata_json["email_ai_generated"] is True
    assert result[0].metadata_json["email_guess_confidence"] == 78
    assert any("Matthias" in w for w in warnings)
    gcm.assert_called_once_with(fast=True, temperature=0.0)
