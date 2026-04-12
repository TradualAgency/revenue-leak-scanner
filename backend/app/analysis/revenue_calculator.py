from decimal import Decimal

BENCHMARK_LOAD_TIME = 0.5  # seconds — "ideal" load time; any time above this costs conversions
LOSS_PER_SECOND = 0.07
MOBILE_SHARE = 0.65
MOBILE_PENALTY = 1.2


def calculate_revenue_loss(monthly_revenue: Decimal, avg_load_time_seconds: float) -> dict:
    """
    Calculate estimated monthly revenue loss due to slow page load times.

    Returns a dict with blended_loss_rate and estimated_monthly_loss.
    """
    excess = max(0.0, avg_load_time_seconds - BENCHMARK_LOAD_TIME)

    desktop_loss = excess * LOSS_PER_SECOND
    mobile_loss = excess * LOSS_PER_SECOND * MOBILE_PENALTY
    blended_loss = (MOBILE_SHARE * mobile_loss) + ((1 - MOBILE_SHARE) * desktop_loss)
    blended_loss = min(blended_loss, 0.50)

    revenue = float(monthly_revenue)
    if blended_loss > 0:
        potential_revenue = revenue / (1 - blended_loss)
    else:
        potential_revenue = revenue

    estimated_monthly_loss = potential_revenue - revenue

    return {
        "blended_loss_rate": round(blended_loss, 4),
        "estimated_monthly_loss": Decimal(str(round(estimated_monthly_loss, 2))),
        "excess_load_time": round(excess, 2),
    }
