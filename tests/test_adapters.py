"""The seam: factory picks the right adapter, and the prod stubs are honest."""

import pytest

from freightvoice.adapters import (
    FakeTMSAdapter,
    get_factoring_adapter,
    get_tms_adapter,
)
from freightvoice.adapters.base import TMSAdapter
from freightvoice.adapters.motive import MotiveAdapter
from freightvoice.adapters.samsara import SamsaraAdapter


def test_factory_returns_fake_by_default():
    assert isinstance(get_tms_adapter("fake"), FakeTMSAdapter)


def test_factory_returns_samsara_stub():
    a = get_tms_adapter("samsara")
    assert isinstance(a, SamsaraAdapter)
    assert isinstance(a, TMSAdapter)


def test_factory_rejects_unknown_backend():
    with pytest.raises(ValueError):
        get_tms_adapter("not_a_tms")


def test_factoring_adapter_available():
    assert get_factoring_adapter().trigger_advance("L1001") == "ADV-L1001"


@pytest.mark.parametrize("adapter", [SamsaraAdapter(), MotiveAdapter()])
def test_prod_stubs_raise_not_implemented(adapter):
    # Stubs exist to prove the seam, not to run — every method is honest.
    with pytest.raises(NotImplementedError):
        adapter.get_load("L1001")
    with pytest.raises(NotImplementedError):
        adapter.trigger_invoice("L1001")
