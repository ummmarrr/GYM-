"""Rules that turn gym data into recommendations.

The findings below are computed, not generated. Each carries the evidence that triggered it,
so an admin can always check the claim. The advisor agent only writes the covering note; if
the model is unavailable the recommendations still stand on their own.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import ClassSchedule, Role, User
from app.services import analytics

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

OVERLOADED_TRAINER_MEMBERS = 15
UNDERUSED_FILL_PERCENT = 40
STRAINED_FILL_PERCENT = 85


@dataclass(frozen=True)
class Recommendation:
    priority: str
    category: str
    title: str
    evidence: str
    action: str
    impact: str


def _fill_percent(row: dict) -> int | None:
    value = row.get("fill")
    if not isinstance(value, str) or not value.endswith("%"):
        return None
    return int(value.removesuffix("%"))


def build_recommendations(db: Session) -> list[Recommendation]:
    metrics = analytics.run_all(db)
    found: list[Recommendation] = []

    renewals = metrics["expiring_soon"]
    if renewals.rows:
        soonest = renewals.rows[0]
        found.append(
            Recommendation(
                priority="high",
                category="Retention",
                title=f"Call {len(renewals.rows)} members before their package expires",
                evidence=(
                    f"{len(renewals.rows)} memberships lapse within "
                    f"{analytics.RENEWAL_WINDOW_DAYS} days, the earliest being "
                    f"{soonest['member']} on {soonest['expires']}."
                ),
                action=(
                    "Work the renewal list from the analyst panel, starting with the "
                    "fewest days left."
                ),
                impact="Renewing an existing member costs far less than acquiring a new one.",
            )
        )

    unfulfilled = metrics["missing_programmes"]
    if unfulfilled.rows:
        found.append(
            Recommendation(
                priority="high",
                category="Service delivery",
                title=f"{len(unfulfilled.rows)} members are paying for a programme they never got",
                evidence=(
                    "These members are on a package that includes a trainer-written programme, "
                    f"but no programme exists for them: "
                    f"{', '.join(row['member'] for row in unfulfilled.rows[:5])}."
                ),
                action="Assign a trainer, then have them publish a workout or diet plan this week.",
                impact="This is the clearest refund and bad-review risk in the data.",
            )
        )

    unassigned = metrics["unassigned_members"]
    entitled_unassigned = [
        row for row in unassigned.rows if row.get("entitled to programme") == "yes"
    ]
    if entitled_unassigned:
        found.append(
            Recommendation(
                priority="high",
                category="Staffing",
                title=f"Assign trainers to {len(entitled_unassigned)} paying members",
                evidence=(
                    f"{len(entitled_unassigned)} members on programme-inclusive packages have no "
                    "trainer against their profile."
                ),
                action="Use the trainer dropdown in the accounts table to assign each one.",
                impact=(
                    "A trainer cannot write a programme for a member who is not assigned to them."
                ),
            )
        )
    elif unassigned.rows:
        found.append(
            Recommendation(
                priority="low",
                category="Staffing",
                title=f"{len(unassigned.rows)} paying members have no trainer",
                evidence="Their packages do not promise a programme, so this is optional.",
                action="Assign trainers if you want to offer check-ins as an upsell.",
                impact="A light touch point that often converts to a higher package.",
            )
        )

    idle = metrics["idle_members"]
    if idle.rows:
        found.append(
            Recommendation(
                priority="medium",
                category="Retention",
                title=f"{len(idle.rows)} paying members have gone quiet",
                evidence=(
                    f"No class booking in {analytics.IDLE_WINDOW_DAYS} days from: "
                    f"{', '.join(row['member'] for row in idle.rows[:5])}."
                ),
                action=(
                    "Send a check-in message and offer to rebook them into a "
                    "beginner-friendly class."
                ),
                impact="Members who stop attending rarely renew, and they usually stop quietly.",
            )
        )

    utilisation = metrics["class_utilisation"]
    for row in utilisation.rows:
        fill = _fill_percent(row)
        if fill is None:
            found.append(
                Recommendation(
                    priority="low",
                    category="Timetable",
                    title=f"No {row['discipline']} classes are scheduled",
                    evidence=f"The timetable has no upcoming {row['discipline']} sessions.",
                    action=(
                        f"Add at least one {row['discipline']} session so the package "
                        "is worth its price."
                    ),
                    impact="Members paying for this discipline currently have nothing to book.",
                )
            )
        elif fill < UNDERUSED_FILL_PERCENT and row["sessions"] > 0:
            found.append(
                Recommendation(
                    priority="medium",
                    category="Timetable",
                    title=f"{row['discipline'].upper()} classes are running {fill}% full",
                    evidence=(
                        f"{row['booked']} of {row['seats']} seats booked across "
                        f"{row['sessions']} sessions."
                    ),
                    action=(
                        "Move these to a busier time slot, or cut a session and promote the rest."
                    ),
                    impact="Empty classes still cost a coach's time.",
                )
            )
        elif fill >= STRAINED_FILL_PERCENT:
            found.append(
                Recommendation(
                    priority="medium",
                    category="Timetable",
                    title=f"{row['discipline'].upper()} classes are nearly full at {fill}%",
                    evidence=f"{row['booked']} of {row['seats']} seats already taken.",
                    action=(
                        "Add another session or raise capacity before members start "
                        "being turned away."
                    ),
                    impact="Demand you can meet today, and a reason to sell more of this package.",
                )
            )

    knowledge = metrics["knowledge_coverage"]
    bare = [row["discipline"] for row in knowledge.rows if row["documents"] == 0]
    if bare:
        found.append(
            Recommendation(
                priority="high" if len(bare) > 2 else "medium",
                category="FitBot quality",
                title=f"FitBot has no source documents for {', '.join(bare)}",
                evidence=(
                    "Retrieval returns nothing for these disciplines, so answers come from the "
                    "model's general knowledge instead of your gym's material."
                ),
                action="Upload your training and nutrition PDFs under the knowledge base section.",
                impact="Grounded answers stop FitBot contradicting what your trainers teach.",
            )
        )

    trainers = metrics["trainer_load"]
    overloaded = [row for row in trainers.rows if row["members"] > OVERLOADED_TRAINER_MEMBERS]
    if overloaded:
        found.append(
            Recommendation(
                priority="medium",
                category="Staffing",
                title=f"{overloaded[0]['trainer']} is carrying {overloaded[0]['members']} members",
                evidence=f"Above the {OVERLOADED_TRAINER_MEMBERS} member guideline per trainer.",
                action="Redistribute members or hire another trainer.",
                impact="Overloaded trainers write generic programmes, which members notice.",
            )
        )

    idle_trainers = [row for row in trainers.rows if row["members"] == 0]
    if idle_trainers and unassigned.rows:
        found.append(
            Recommendation(
                priority="medium",
                category="Staffing",
                title=f"{len(idle_trainers)} trainers have no members while others go unassigned",
                evidence=(
                    f"Unassigned members: {len(unassigned.rows)}. Trainers with nobody: "
                    f"{', '.join(row['trainer'] for row in idle_trainers[:5])}."
                ),
                action="Assign the waiting members to these trainers.",
                impact="You are paying for capacity you are not using.",
            )
        )

    if not db.scalars(select(User).where(User.role == Role.TRAINER)).first():
        found.append(
            Recommendation(
                priority="high",
                category="Staffing",
                title="There are no trainers on the roster",
                evidence="No account holds the trainer role.",
                action="Create a trainer account from the admin console.",
                impact="Without a trainer nobody can write programmes or run classes.",
            )
        )

    upcoming = db.scalars(
        select(ClassSchedule).where(ClassSchedule.starts_at >= _now_floor())
    ).all()
    if not upcoming:
        found.append(
            Recommendation(
                priority="high",
                category="Timetable",
                title="The timetable is empty",
                evidence="No classes are scheduled in the future.",
                action="Add sessions for the coming week so members have something to book.",
                impact="Class access is the main thing members pay for.",
            )
        )

    growth = metrics["signup_trend"]
    if growth.rows and len(growth.rows) >= 2:
        this_month = growth.rows[-1]["new members"]
        last_month = growth.rows[-2]["new members"]
        if this_month == 0 and last_month == 0:
            found.append(
                Recommendation(
                    priority="medium",
                    category="Growth",
                    title="No new signups in the last two months",
                    evidence="Registrations were zero this month and last month.",
                    action="Run a referral offer for existing members, or a free trial week.",
                    impact="Without new signups, revenue only falls as packages lapse.",
                )
            )
        elif this_month < last_month:
            found.append(
                Recommendation(
                    priority="low",
                    category="Growth",
                    title=f"Signups slowed from {last_month} to {this_month} this month",
                    evidence="Month-on-month registrations are down.",
                    action="Check whether the pricing page or a campaign changed recently.",
                    impact="Catching a dip early is cheaper than reversing a trend.",
                )
            )

    found.sort(key=lambda item: PRIORITY_ORDER.get(item.priority, 3))
    return found


def _now_floor():
    from app.db import utc_now

    return utc_now()


def summarise(recommendations: list[Recommendation]) -> str:
    if not recommendations:
        return "No issues found. Every check the advisor runs came back clean."
    counts = dict.fromkeys(PRIORITY_ORDER, 0)
    for item in recommendations:
        counts[item.priority] = counts.get(item.priority, 0) + 1
    parts = [f"{counts[level]} {level}" for level in PRIORITY_ORDER if counts.get(level)]
    return f"{len(recommendations)} recommendations: {', '.join(parts)} priority."


def horizon_note() -> str:
    end = date.today() + timedelta(days=analytics.RENEWAL_WINDOW_DAYS)
    return f"Renewal window checked up to {end:%d %b %Y}."
