"""Legacy rank ladder with provisional figures (see docs/open-questions.md).

Personal tokens increase monotonically so the legacy entrepreneurial-difference
calculation is meaningful. Volume thresholds are unconfirmed promotion figures,
measured as lifetime cumulative totals rather than over a rolling window."""

RULE_VERSION = "2026.1-placeholder"

RANK_SEED = [
    {"code": "SP1", "name": "SosPromoter 1", "level": 1, "personal_token_cents": 4000, "personal_volume_threshold_cents": 0, "group_volume_threshold_cents": 0},
    {"code": "SP2", "name": "SosPromoter 2", "level": 2, "personal_token_cents": 4500, "personal_volume_threshold_cents": 1500, "group_volume_threshold_cents": 1500},
    {"code": "SP3", "name": "SosPromoter 3", "level": 3, "personal_token_cents": 5000, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 4000},
    {"code": "SL1", "name": "SosLeader 1", "level": 4, "personal_token_cents": 5500, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 8000},
    {"code": "SL2", "name": "SosLeader 2", "level": 5, "personal_token_cents": 6000, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 12000},
    {"code": "SL3", "name": "SosLeader 3", "level": 6, "personal_token_cents": 6500, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 16000},
    {"code": "SL4", "name": "SosLeader 4", "level": 7, "personal_token_cents": 7000, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 20000},
    {"code": "SM1", "name": "SosManager 1", "level": 8, "personal_token_cents": 7500, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 25000},
    {"code": "SM2", "name": "SosManager 2", "level": 9, "personal_token_cents": 8000, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 30000},
    {"code": "SM3", "name": "SosManager 3", "level": 10, "personal_token_cents": 8500, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 35000},
    {"code": "SM4", "name": "SosManager 4", "level": 11, "personal_token_cents": 9000, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 40000},
    {"code": "SM5", "name": "SosManager 5", "level": 12, "personal_token_cents": 9500, "personal_volume_threshold_cents": 3000, "group_volume_threshold_cents": 45000},
]
