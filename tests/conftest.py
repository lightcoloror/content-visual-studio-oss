"""No services, private voice material, or external network in synthetic tests."""
import os
import socket
import sys
from pathlib import Path
import pytest
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
os.environ["CONTENT_STUDIO_HUMAN_VOICE_ROOT"]=str(ROOT/"fixtures/synthetic-voice")

@pytest.fixture(autouse=True)
def offline_tests(monkeypatch,tmp_path):
    monkeypatch.setenv("CONTENT_CANDIDATE_TEST_ROOT",str(tmp_path))
    for name in ("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","http_proxy","https_proxy","all_proxy"):
        monkeypatch.delenv(name,raising=False)
    monkeypatch.setenv("NO_PROXY","*")
    allowed={"127.0.0.1","::1","localhost",None}
    original_dns=socket.getaddrinfo
    original_create=socket.create_connection
    original_connect=socket.socket.connect
    def dns(host,*args,**kwargs):
        if host not in allowed:raise OSError("External DNS is disabled in synthetic tests")
        return original_dns(host,*args,**kwargs)
    def create(address,*args,**kwargs):
        if address[0] not in allowed:raise OSError("External connections are disabled in synthetic tests")
        return original_create(address,*args,**kwargs)
    def connect(sock,address):
        if not isinstance(address,tuple) or address[0] not in allowed:
            raise OSError("External connections are disabled in synthetic tests")
        return original_connect(sock,address)
    monkeypatch.setattr(socket,"getaddrinfo",dns)
    monkeypatch.setattr(socket,"create_connection",create)
    monkeypatch.setattr(socket.socket,"connect",connect)


def pytest_collection_modifyitems(items):
    """Keep unavailable external-owner tests visible as explicit skips."""
    mvp_tests={
        "test_existing_mvp_video_consumer_accepts_and_dry_runs",
        "test_downstream_timeout_fails_closed",
        "test_single_command_e2e_is_stable_across_repeated_runs",
        "test_single_command_e2e_recovers_from_expected_partial_output",
        "test_single_command_e2e_refuses_unmanaged_output",
    }
    owner_tests={
        "test_valid_owner_card_cannot_be_substituted_for_another_fact_revision",
        "test_current_owner_card_and_sentence_review_allow_only_synthetic_draft",
    }
    for item in items:
        if item.name in mvp_tests and not (ROOT/"mvp-video-pipeline/scripts/content_video.py").is_file():
            item.add_marker(pytest.mark.skip(reason="Optional MVP owner entry is not distributed in this edition; integration remains unverified"))
        if item.name in owner_tests and not (ROOT.parent/"self-media-creation-system/scripts/story_design_gate.py").is_file():
            item.add_marker(pytest.mark.skip(reason="Optional self-media owner entry is not available; owner integration remains unverified"))
