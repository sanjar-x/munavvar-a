from datetime import date, timedelta


def month_ago(ref: date) -> date:
    """30 дней назад от ref — общий хелпер для dashboard."""
    return ref - timedelta(days=30)
