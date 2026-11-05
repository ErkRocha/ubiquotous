import random
from collections import Counter

import pytest

from app.balancers import PickContext, make_balancer
from app.balancers.ip_hash import IpHash
from app.balancers.least_connections import LeastConnections
from app.balancers.least_time import LeastTime
from app.balancers.random_two_choices import RandomTwoChoices
from app.balancers.round_robin import RoundRobin
from app.balancers.sticky_round_robin import StickyRoundRobin

from .helpers import upstreams


def names(picks):
    return [u.name for u in picks]


def test_round_robin_cycles_in_order():
    pool = upstreams("a", "b", "c")
    rr = RoundRobin("p")
    assert names(rr.pick(pool, PickContext()) for _ in range(6)) == ["a", "b", "c", "a", "b", "c"]


def test_sticky_round_robin_sets_cookie_then_sticks():
    pool = upstreams("a", "b", "c")
    sticky = StickyRoundRobin("all")

    first = sticky.pick(pool, PickContext())
    cookies = sticky.response_cookies(first, PickContext())
    assert cookies == {"gw_sticky_all": first.name}

    ctx = PickContext(cookies=cookies)
    assert {sticky.pick(pool, ctx).name for _ in range(10)} == {first.name}
    assert sticky.response_cookies(first, ctx) == {}


def test_sticky_round_robin_moves_when_upstream_is_unavailable():
    a, b, c = upstreams("a", "b", "c")
    sticky = StickyRoundRobin("all")
    ctx = PickContext(cookies={"gw_sticky_all": "a"})
    other = sticky.pick([b, c], ctx)
    assert other.name in {"b", "c"}
    assert sticky.response_cookies(other, ctx) == {"gw_sticky_all": other.name}


def test_least_connections_picks_the_least_busy():
    a, b, c = upstreams("a", "b", "c")
    a.active_connections, b.active_connections, c.active_connections = 3, 1, 2
    assert LeastConnections("p").pick([a, b, c], PickContext()) is b


def test_least_connections_breaks_ties_randomly():
    pool = upstreams("a", "b", "c")
    lc = LeastConnections("p", random.Random(1))
    assert set(names(lc.pick(pool, PickContext()) for _ in range(50))) == {"a", "b", "c"}


def test_least_time_prefers_fast_and_tries_unmeasured_first():
    a, b, c = upstreams("a", "b", "c")
    a.latency_ewma_ms, b.latency_ewma_ms = 50, 10
    lt = LeastTime("p")
    assert lt.pick([a, b, c], PickContext()) is c  # sem medição ainda
    c.latency_ewma_ms = 30
    assert lt.pick([a, b, c], PickContext()) is b


def test_least_time_weighs_active_connections():
    fast, slow = upstreams("fast", "slow")
    fast.latency_ewma_ms, fast.active_connections = 10, 4  # 10 * 5 = 50
    slow.latency_ewma_ms, slow.active_connections = 30, 0  # 30 * 1 = 30
    assert LeastTime("p").pick([fast, slow], PickContext()) is slow


def test_ip_hash_is_stable_per_client():
    pool = upstreams("a", "b", "c", "d")
    ih = IpHash("p")
    for ip in ("10.0.0.1", "10.0.0.2", "192.168.1.50"):
        ctx = PickContext(client_ip=ip, pool=pool)
        assert len({ih.pick(pool, ctx).name for _ in range(10)}) == 1


def test_ip_hash_spreads_neighbor_ips():
    pool = upstreams("a", "b", "c", "d", "e", "f")
    ih = IpHash("p")
    picks = {ih.pick(pool, PickContext(client_ip=f"10.0.0.{i}", pool=pool)).name for i in range(1, 13)}
    assert len(picks) >= 4


def test_ip_hash_only_remaps_clients_of_the_failed_upstream():
    pool = upstreams("a", "b", "c", "d")
    ih = IpHash("p")
    ips = [f"10.0.0.{i}" for i in range(100)]
    before = {ip: ih.pick(pool, PickContext(client_ip=ip, pool=pool)) for ip in ips}

    down = pool[1]
    available = [u for u in pool if u is not down]
    after = {ip: ih.pick(available, PickContext(client_ip=ip, pool=pool)) for ip in ips}

    for ip in ips:
        if before[ip] is not down:
            assert after[ip] is before[ip]


def test_random_two_choices_picks_the_less_loaded_of_the_pair():
    busy, idle = upstreams("busy", "idle")
    busy.active_connections = 5
    r2 = RandomTwoChoices("p", random.Random(7))
    assert {r2.pick([busy, idle], PickContext()).name for _ in range(20)} == {"idle"}


def test_random_two_choices_spreads_load():
    pool = upstreams("a", "b", "c", "d")
    r2 = RandomTwoChoices("p", random.Random(3))
    counts = Counter(names(r2.pick(pool, PickContext()) for _ in range(400)))
    assert set(counts) == {"a", "b", "c", "d"}


def test_make_balancer_rejects_unknown_strategy():
    with pytest.raises(ValueError, match="round_robin"):
        make_balancer("fastest", "p")
