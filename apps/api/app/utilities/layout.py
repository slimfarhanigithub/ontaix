"""Canvas geometry shared with the Studio: company row, domain ring and birth positions."""

from __future__ import annotations

import math

CELL = 24.0
DOMAIN_COUNT = 9
DOMAIN_R = max(470.0, DOMAIN_COUNT * 74.0)
COMPANY_GAP = 2 * DOMAIN_R + 1100
BIRTH_DISTANCE = CELL * 3.1
BIRTH_ANGLE_NOISE = 1.2
ROOT_COLOR = "#d8deee"
NEUTRAL_COLOR = "#a9b3cc"
CONFLICT_COLOR = "#d95a68"

REST_ISA_SAME_DOMAIN = 170
REST_ISA_CROSS_DOMAIN = 300
REST_REL_SAME_DOMAIN = 220
REST_REL_CROSS_DOMAIN = 330
REST_CROSS_COMPANY = 560
REST_CLASH = 130


def company_centre(position: int, company_count: int) -> tuple[float, float]:
    """Companies sit on one horizontal row centred on the origin."""
    return ((position - (company_count - 1) / 2) * COMPANY_GAP, 0.0)


def domain_centre(company_xy: tuple[float, float], template_position: int) -> tuple[float, float]:
    """Domain products sit on a ring around the company, Production at the top."""
    angle = -math.pi / 2 + template_position * 2 * math.pi / DOMAIN_COUNT
    return (
        company_xy[0] + math.cos(angle) * DOMAIN_R,
        company_xy[1] + math.sin(angle) * DOMAIN_R,
    )


def birth_position(
    parent_xy: tuple[float, float],
    target_xy: tuple[float, float] | None,
    noise: float,
) -> tuple[float, float]:
    """Where a newborn cell settles after dividing from its parent toward its domain centre.

    `noise` is a unit draw from the injected randomness; it becomes the angle jitter.
    """
    if target_xy is None:
        angle = noise * 2 * math.pi
    else:
        angle = math.atan2(target_xy[1] - parent_xy[1], target_xy[0] - parent_xy[0])
        angle += (noise - 0.5) * BIRTH_ANGLE_NOISE
    return (
        parent_xy[0] + math.cos(angle) * BIRTH_DISTANCE,
        parent_xy[1] + math.sin(angle) * BIRTH_DISTANCE,
    )


def rest_length(kind: str, cross_domain: bool, cross_company: bool) -> int:
    """Spring rest length of a relation, by kind and by how far it reaches."""
    if cross_company:
        return REST_CROSS_COMPANY
    if kind == "isa":
        return REST_ISA_CROSS_DOMAIN if cross_domain else REST_ISA_SAME_DOMAIN
    if kind == "clash":
        return REST_CLASH
    return REST_REL_CROSS_DOMAIN if cross_domain else REST_REL_SAME_DOMAIN
