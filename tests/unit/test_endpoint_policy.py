"""Unit tests for security/endpoint_policy.py (Fase 1, SEC-4) — the
location-based classifier that replaced the old provider-name check."""
from security.endpoint_policy import is_internal_endpoint


def test_loopback_ipv4_is_internal():
    assert is_internal_endpoint("http://127.0.0.1:11434") is True


def test_loopback_ipv6_is_internal():
    assert is_internal_endpoint("http://[::1]:11434") is True


def test_localhost_hostname_is_internal():
    assert is_internal_endpoint("http://localhost:11434") is True


def test_wsl_docker_compose_private_ip_is_internal():
    """This deployment's actual Docker Compose OLLAMA_BASE_URL value."""
    assert is_internal_endpoint("http://172.29.239.93:11434") is True


def test_rfc1918_10_range_is_internal():
    assert is_internal_endpoint("http://10.0.5.2:11434") is True


def test_rfc1918_192_168_range_is_internal():
    assert is_internal_endpoint("http://192.168.1.50:11434") is True


def test_kubernetes_cluster_local_suffix_is_internal():
    """This deployment's actual k8s configmap OLLAMA_BASE_URL value."""
    assert is_internal_endpoint("http://ollama.ai-engine.svc.cluster.local:11434") is True


def test_dot_local_suffix_is_internal():
    assert is_internal_endpoint("http://my-ollama.local:11434") is True


def test_dot_internal_suffix_is_internal():
    assert is_internal_endpoint("http://ollama.internal:11434") is True


def test_public_hostname_is_external():
    assert is_internal_endpoint("https://api.openai.com/v1") is False


def test_public_ip_is_external():
    assert is_internal_endpoint("http://8.8.8.8:11434") is False


def test_anthropic_and_gemini_hosts_are_external():
    assert is_internal_endpoint("https://api.anthropic.com") is False
    assert is_internal_endpoint("https://generativelanguage.googleapis.com") is False


def test_empty_url_is_treated_as_external_fail_closed():
    assert is_internal_endpoint("") is False


def test_unparseable_url_is_treated_as_external_fail_closed():
    assert is_internal_endpoint("not a url at all") is False
