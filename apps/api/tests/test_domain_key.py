"""Pure rules of tenant domains: the key derived from a name, and where custom domains sit."""

from __future__ import annotations

import math

from app.utilities.domain_key import derive_domain_key
from app.utilities.layout import CUSTOM_RING_STEP, DOMAIN_R, domain_centre


def test_domain_keys_are_derived_from_names() -> None:
    assert derive_domain_key("Customer care", ()) == "customer_care"
    assert derive_domain_key("  R&D / Labs  ", ()) == "r_d_labs"
    assert derive_domain_key("Sales", ("sales",)) == "sales_2"
    assert derive_domain_key("Sales", ("sales", "sales_2")) == "sales_3"
    assert derive_domain_key("3PL", ()) == "d_3pl"
    assert derive_domain_key("Ünïcode", ()) == "unicode"
    assert derive_domain_key("X", ()) == "x_domain"
    assert derive_domain_key("日本", ()) == "domain"
    long_key = derive_domain_key("a" * 80, ())
    assert len(long_key) == 40
    assert len(derive_domain_key("a" * 80, (long_key,))) == 40


def test_custom_domain_positions_sit_outside_the_template_ring() -> None:
    centre = (100.0, -50.0)
    templates = [domain_centre(centre, p) for p in range(9)]
    assert all(math.isclose(math.dist(centre, t), DOMAIN_R) for t in templates)
    assert math.isclose(templates[0][0], 100.0) and math.isclose(templates[0][1], -50 - DOMAIN_R)
    first_custom = domain_centre(centre, 9)
    assert math.isclose(math.dist(centre, first_custom), DOMAIN_R)
    angle = math.atan2(first_custom[1] - centre[1], first_custom[0] - centre[0])
    assert math.isclose(angle, -math.pi / 2 + 0.5 * 2 * math.pi / 9)
    outer = domain_centre(centre, 18)
    assert math.isclose(math.dist(centre, outer), DOMAIN_R + CUSTOM_RING_STEP)
    last = domain_centre(centre, 63)
    assert math.isclose(math.dist(centre, last), DOMAIN_R + 6 * CUSTOM_RING_STEP)
