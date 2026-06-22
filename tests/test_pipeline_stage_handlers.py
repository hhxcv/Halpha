from __future__ import annotations

from halpha.pipeline_stage_handlers import default_stage_handlers
from halpha.pipeline_stages import STAGE_ORDER
from halpha.stage_handlers import DOMAIN_STAGE_HANDLER_FACTORIES, domain_stage_handlers


def test_default_stage_handlers_cover_stage_order_without_fallbacks() -> None:
    handlers = default_stage_handlers()

    assert list(handlers) == list(STAGE_ORDER)
    assert all("_unimplemented_handler" not in handler.__qualname__ for handler in handlers.values())


def test_domain_stage_handler_registries_are_disjoint_and_complete() -> None:
    seen: dict[str, str] = {}

    for factory, handlers in zip(DOMAIN_STAGE_HANDLER_FACTORIES, domain_stage_handlers(), strict=True):
        assert handlers
        overlap = set(handlers) & set(seen)
        assert not overlap, f"{factory.__module__}.{factory.__name__} duplicates {sorted(overlap)}"
        for stage in handlers:
            seen[stage] = factory.__module__

    assert set(seen) == set(STAGE_ORDER)


def test_default_stage_handlers_apply_overrides_after_domain_groups() -> None:
    def replacement(config, run) -> list[str]:
        return []

    handlers = default_stage_handlers({"collect_market_data": replacement})

    assert handlers["collect_market_data"] is replacement
