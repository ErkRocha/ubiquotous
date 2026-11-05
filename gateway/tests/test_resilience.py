from app.cache import ResponseCache
from app.circuit_breaker import CLOSED, HALF_OPEN, OPEN, CircuitBreaker
from app.rate_limit import TokenBucketLimiter

from .helpers import FakeClock

# ---------------------------------------------------------------- circuit breaker


def test_circuit_opens_after_consecutive_failures():
    cb = CircuitBreaker("x", failure_threshold=3, open_seconds=10, clock=FakeClock())
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CLOSED and cb.allows_request()
    cb.record_failure()
    assert cb.state == OPEN and not cb.allows_request()


def test_success_resets_failure_count():
    cb = CircuitBreaker("x", failure_threshold=3, clock=FakeClock())
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    assert cb.state == CLOSED


def test_half_open_allows_a_single_trial_then_closes_on_success():
    clock = FakeClock()
    cb = CircuitBreaker("x", failure_threshold=1, open_seconds=10, clock=clock)
    cb.record_failure()
    clock.now += 9
    assert cb.state == OPEN and cb.retry_in() == 1
    clock.now += 1
    assert cb.state == HALF_OPEN and cb.allows_request()

    cb.before_request()
    assert not cb.allows_request()  # só uma requisição de teste por vez
    cb.record_success()
    assert cb.state == CLOSED and cb.allows_request()


def test_half_open_reopens_on_failure():
    clock = FakeClock()
    cb = CircuitBreaker("x", failure_threshold=1, open_seconds=10, clock=clock)
    cb.record_failure()
    clock.now += 10
    cb.before_request()
    cb.record_failure()
    assert cb.state == OPEN and cb.retry_in() == 10


# ---------------------------------------------------------------- rate limit


def test_token_bucket_allows_burst_then_blocks():
    limiter = TokenBucketLimiter(capacity=3, refill_per_second=1, clock=FakeClock())
    assert [limiter.check("ip").allowed for _ in range(4)] == [True, True, True, False]
    blocked = limiter.check("ip")
    assert blocked.remaining == 0 and blocked.retry_after == 1
    assert limiter.rejected == 2


def test_token_bucket_refills_over_time():
    clock = FakeClock()
    limiter = TokenBucketLimiter(capacity=2, refill_per_second=2, clock=clock)
    limiter.check("ip")
    limiter.check("ip")
    assert not limiter.check("ip").allowed
    clock.now += 0.5  # +1 ficha
    assert limiter.check("ip").allowed
    assert not limiter.check("ip").allowed


def test_token_bucket_is_per_client():
    limiter = TokenBucketLimiter(capacity=1, refill_per_second=1, clock=FakeClock())
    assert limiter.check("a").allowed
    assert not limiter.check("a").allowed
    assert limiter.check("b").allowed


# ---------------------------------------------------------------- cache


def test_cache_expires_after_ttl():
    clock = FakeClock()
    cache = ResponseCache(ttl_seconds=5, clock=clock)
    key = cache.key("all", "/users", "")
    cache.put(key, "/users", 200, {}, b"[]")
    clock.now += 4
    assert cache.get(key).body == b"[]"
    assert cache.age(cache.get(key)) == 4
    clock.now += 1
    assert cache.get(key) is None


def test_cache_invalidates_the_whole_resource():
    cache = ResponseCache(ttl_seconds=60, clock=FakeClock())
    for path in ("/users", "/users/1", "/users/2"):
        cache.put(cache.key("all", path, ""), path, 200, {}, b"")
    cache.put(cache.key("all", "/health", ""), "/health", 200, {}, b"")
    assert cache.invalidate("/users/1") == 3
    assert list(cache.entries) == ["all GET /health"]


def test_cache_evicts_oldest_when_full():
    cache = ResponseCache(ttl_seconds=60, max_entries=2, clock=FakeClock())
    for path in ("/a", "/b", "/c"):
        cache.put(cache.key("p", path, ""), path, 200, {}, b"")
    assert list(cache.entries) == ["p GET /b", "p GET /c"]
