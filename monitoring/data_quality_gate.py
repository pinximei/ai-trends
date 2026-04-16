from dataclasses import dataclass


@dataclass
class QualityMetrics:
    duplicate_rate: float
    missing_key_field_rate: float
    daily_success_rate: float


def validate(metrics: QualityMetrics):
    errors = []
    if metrics.duplicate_rate > 0.15:
        errors.append("duplicate_rate too high")
    if metrics.missing_key_field_rate > 0.10:
        errors.append("missing_key_field_rate too high")
    if metrics.daily_success_rate < 0.95:
        errors.append("daily_success_rate too low")
    return errors


if __name__ == "__main__":
    report = validate(QualityMetrics(0.05, 0.04, 1.0))
    print("OK" if not report else "; ".join(report))
