"""
Phase 7: Revenue Engine & Billing
Stripe integration, subscription management, metered billing.
"""
import os
import logging
import asyncio
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import hmac

logger = logging.getLogger(__name__)

# ─────── [P7.1] SUBSCRIPTION TIERS ─────────
SUBSCRIPTION_TIERS = {
    "free": {
        "name": "Free Tier",
        "price": 0.00,
        "billing_cycle": "monthly",
        "limits": {
            "leads_per_month": 100,
            "emails_per_month": 50,
            "calls_per_month": 0,
            "meeting_bookings": 0,
            "api_calls_per_day": 100,
        },
        "features": [
            "AI lead generation",
            "Basic outreach templates",
            "Email forwarding",
            "Google Sheets sync",
            "Email support (48h)",
        ],
    },
    "starter": {
        "name": "Starter",
        "price": 99.00,
        "billing_cycle": "monthly",
        "limits": {
            "leads_per_month": 1000,
            "emails_per_month": 500,
            "calls_per_month": 50,
            "meeting_bookings": 20,
            "api_calls_per_day": 1000,
        },
        "features": [
            "Everything in Free",
            "Advanced lead scoring",
            "Campaign automation",
            "Call recording (Retell AI)",
            "Dedicated Slack channel",
            "Email support (24h)",
        ],
    },
    "pro": {
        "name": "Pro",
        "price": 299.00,
        "billing_cycle": "monthly",
        "limits": {
            "leads_per_month": 5000,
            "emails_per_month": 2000,
            "calls_per_month": 200,
            "meeting_bookings": 100,
            "api_calls_per_day": 5000,
        },
        "features": [
            "Everything in Starter",
            "Custom AI personas",
            "Webhook integrations",
            "Bulk lead import",
            "Priority phone support",
            "Custom domain setup",
        ],
    },
    "enterprise": {
        "name": "Enterprise",
        "price": None,  # Custom pricing
        "billing_cycle": "custom",
        "limits": {
            "leads_per_month": 50000,
            "emails_per_month": 10000,
            "calls_per_month": 1000,
            "meeting_bookings": 500,
            "api_calls_per_day": 50000,
        },
        "features": [
            "Everything in Pro",
            "Dedicated account manager",
            "SLA agreement",
            "Custom integrations",
            "On-premise deployment option",
            "White-label solution",
        ],
    },
}

# ─────── [P7.2] STRIPE CLIENT WRAPPER ─────────
class StripePaymentManager:
    """
    Wrapper around Stripe API for subscription and billing management.
    Handles payment processing, subscription management, and webhooks.
    """
    
    def __init__(self):
        self.api_key = os.getenv("STRIPE_SECRET_KEY")
        self.publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY")
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        self.client = None
        
        if self.api_key:
            try:
                import stripe
                stripe.api_key = self.api_key
                self.client = stripe
                logger.info("[+] Stripe client initialized")
            except Exception as e:
                logger.warning(f"[-] Stripe init failed: {e}")
    
    async def create_payment_intent(self, amount_cents: int, customer_id: str, 
                                   description: str = "") -> Dict:
        """Create a payment intent for one-time payment."""
        if not self.client:
            return {"success": False, "error": "Stripe not configured"}
        
        try:
            intent = await asyncio.to_thread(
                self.client.PaymentIntent.create,
                amount=amount_cents,
                currency="usd",
                customer=customer_id,
                description=description,
                metadata={"timestamp": datetime.utcnow().isoformat()},
            )
            
            return {
                "success": True,
                "client_secret": intent.client_secret,
                "intent_id": intent.id,
                "amount": intent.amount,
            }
        except Exception as e:
            logger.error(f"[Stripe] PaymentIntent creation failed: {e}")
            return {"success": False, "error": str(e)[:200]}
    
    async def create_subscription(self, customer_id: str, price_id: str) -> Dict:
        """Create a subscription for a customer."""
        if not self.client:
            return {"success": False, "error": "Stripe not configured"}
        
        try:
            subscription = await asyncio.to_thread(
                self.client.Subscription.create,
                customer=customer_id,
                items=[{"price": price_id}],
                payment_behavior="default_incomplete",
                expand=["latest_invoice.payment_intent"],
            )
            
            return {
                "success": True,
                "subscription_id": subscription.id,
                "status": subscription.status,
                "current_period_start": subscription.current_period_start,
                "current_period_end": subscription.current_period_end,
            }
        except Exception as e:
            logger.error(f"[Stripe] Subscription creation failed: {e}")
            return {"success": False, "error": str(e)[:200]}
    
    async def cancel_subscription(self, subscription_id: str) -> Dict:
        """Cancel subscription at end of billing period."""
        if not self.client:
            return {"success": False, "error": "Stripe not configured"}
        
        try:
            subscription = await asyncio.to_thread(
                self.client.Subscription.modify,
                subscription_id,
                cancel_at_period_end=True,
            )
            
            return {
                "success": True,
                "subscription_id": subscription.id,
                "cancel_at": subscription.cancel_at,
                "status": subscription.status,
            }
        except Exception as e:
            logger.error(f"[Stripe] Subscription cancel failed: {e}")
            return {"success": False, "error": str(e)[:200]}
    
    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """Verify Stripe webhook signature for security."""
        if not self.webhook_secret:
            return False
        
        try:
            expected_sig = hmac.new(
                self.webhook_secret.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected_sig, signature)
        except Exception as e:
            logger.warning(f"[Stripe] Webhook verification failed: {e}")
            return False

# ─────── [P7.3] USAGE-BASED BILLING ─────────
class MeteredBillingManager:
    """
    Manage usage-based (metered) billing.
    Tracks API calls, emails sent, calls made, etc.
    Reports usage to Stripe for billing.
    """
    
    def __init__(self, db_func):
        self.db = db_func
        self.current_usage = {}
    
    async def track_usage(self, client_id: int, metric: str, quantity: int = 1):
        """Track usage for billing purposes."""
        
        # Increment in-memory counter
        key = f"{client_id}:{metric}"
        self.current_usage[key] = self.current_usage.get(key, 0) + quantity
        
        # Log to database for auditing
        await self.db(
            """
            INSERT INTO usage_log (client_id, metric, quantity, logged_at)
            VALUES (?, ?, ?, ?)
            """,
            (client_id, metric, quantity, datetime.utcnow().isoformat())
        )
        
        # Check if user has exceeded limits
        tier = await self._get_user_tier(client_id)
        limits = SUBSCRIPTION_TIERS[tier]["limits"]
        
        # Get current month usage
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        row = await self.db(
            """
            SELECT SUM(quantity) as total
            FROM usage_log
            WHERE client_id = ? AND metric = ? AND logged_at >= ?
            """,
            (client_id, metric, month_start.isoformat()),
            fetchone=True
        )
        
        month_total = row["total"] if row and row["total"] else 0
        limit = limits.get(f"{metric}_per_month", 999999)
        
        if month_total > limit:
            logger.warning(f"[METERED] Client {client_id} exceeded {metric} limit ({month_total}/{limit})")
            # TODO: Trigger overage charges or rate limiting
    
    async def _get_user_tier(self, client_id: int) -> str:
        """Get user's current subscription tier."""
        result = await self.db(
            "SELECT subscription_tier FROM users WHERE id = ?",
            (client_id,),
            fetchone=True
        )
        return result["subscription_tier"] if result else "free"
    
    async def get_monthly_usage(self, client_id: int) -> Dict:
        """Get current month's usage."""
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        rows = await self.db(
            """
            SELECT metric, SUM(quantity) as total
            FROM usage_log
            WHERE client_id = ? AND logged_at >= ?
            GROUP BY metric
            """,
            (client_id, month_start.isoformat()),
            fetchall=True
        )
        
        usage = {}
        for row in rows:
            usage[row["metric"]] = row["total"]
        
        return usage
    
    async def generate_invoice(self, client_id: int, month: int = None, year: int = None) -> Dict:
        """Generate invoice for a client for specified month."""
        if month is None:
            now = datetime.utcnow()
            month, year = now.month - 1, now.year
            if month == 0:
                month, year = 12, year - 1
        
        month_start = datetime(year, month, 1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
        
        # Get user info
        user = await self.db(
            "SELECT * FROM users WHERE id = ?",
            (client_id,),
            fetchone=True
        )
        
        # Get usage for month
        rows = await self.db(
            """
            SELECT metric, SUM(quantity) as total
            FROM usage_log
            WHERE client_id = ? AND logged_at BETWEEN ? AND ?
            GROUP BY metric
            """,
            (client_id, month_start.isoformat(), month_end.isoformat()),
            fetchall=True
        )
        
        # Calculate line items
        tier = user["subscription_tier"]
        subscription_price = SUBSCRIPTION_TIERS[tier]["price"]
        
        line_items = [
            {
                "description": f"{tier.title()} Subscription",
                "amount": Decimal(str(subscription_price)),
            }
        ]
        
        # Add overage charges if applicable
        total_overage = Decimal("0")
        for row in rows:
            metric = row["metric"]
            usage = row["total"]
            limit = SUBSCRIPTION_TIERS[tier]["limits"].get(f"{metric}_per_month", 999999)
            
            if usage > limit:
                # $0.01 per overage unit (configurable)
                overage_charge = Decimal(str(usage - limit)) * Decimal("0.01")
                total_overage += overage_charge
                line_items.append({
                    "description": f"{metric} overage ({usage - limit} units @ $0.01)",
                    "amount": overage_charge,
                })
        
        total = Decimal(str(subscription_price)) + total_overage
        
        return {
            "invoice_id": f"INV-{client_id}-{year}-{month:02d}",
            "client_id": client_id,
            "period_start": month_start.isoformat(),
            "period_end": month_end.isoformat(),
            "line_items": line_items,
            "subtotal": Decimal(str(subscription_price)),
            "overage_charges": total_overage,
            "total": total,
            "status": "draft",
        }

# ─────── [P7.4] SUBSCRIPTION MANAGER ─────────
class SubscriptionManager:
    """
    High-level subscription management:
    - Upgrade/downgrade
    - Churn prevention
    - Retention analytics
    - Renewal reminders
    """
    
    def __init__(self, stripe_client: StripePaymentManager, db_func):
        self.stripe = stripe_client
        self.db = db_func
    
    async def upgrade_subscription(self, client_id: int, new_tier: str) -> Dict:
        """Upgrade user subscription to higher tier."""
        
        # Get current subscription
        user = await self.db(
            "SELECT * FROM users WHERE id = ?",
            (client_id,),
            fetchone=True
        )
        
        old_tier = user["subscription_tier"]
        old_price = SUBSCRIPTION_TIERS[old_tier]["price"]
        new_price = SUBSCRIPTION_TIERS[new_tier]["price"]
        
        # Calculate credit for remaining period
        subscription_end = datetime.fromisoformat(user["subscription_period_end"])
        days_remaining = (subscription_end - datetime.utcnow()).days
        daily_rate = old_price / 30
        credit = daily_rate * days_remaining
        
        # Charge difference
        amount_due = (new_price - credit) * 100  # Convert to cents
        
        if amount_due > 0:
            payment_result = await self.stripe.create_payment_intent(
                int(amount_due),
                user["stripe_customer_id"],
                f"Upgrade from {old_tier} to {new_tier}"
            )
            
            if not payment_result.get("success"):
                return payment_result
        
        # Update subscription in database
        await self.db(
            """
            UPDATE users
            SET subscription_tier = ?, subscription_updated_at = ?
            WHERE id = ?
            """,
            (new_tier, datetime.utcnow().isoformat(), client_id)
        )
        
        logger.info(f"[BILLING] Client {client_id} upgraded {old_tier} → {new_tier}")
        
        return {
            "success": True,
            "old_tier": old_tier,
            "new_tier": new_tier,
            "credit": credit,
            "amount_due": amount_due / 100,
        }
    
    async def check_renewal_upcoming(self, days_before: int = 7) -> List[int]:
        """Get list of client IDs with subscriptions renewing in N days."""
        cutoff = (datetime.utcnow() + timedelta(days=days_before)).isoformat()
        
        rows = await self.db(
            """
            SELECT id FROM users
            WHERE subscription_tier != 'free'
            AND subscription_period_end <= ?
            AND renewal_reminder_sent = FALSE
            """,
            (cutoff,),
            fetchall=True
        )
        
        return [row["id"] for row in rows]

# ─────── [P7.5] REVENUE ANALYTICS ─────────
class RevenueAnalytics:
    """
    Revenue analytics and business intelligence.
    - MRR (Monthly Recurring Revenue)
    - ARR (Annual Recurring Revenue)
    - Churn rate
    - LTV (Lifetime Value)
    - CAC (Customer Acquisition Cost)
    """
    
    def __init__(self, db_func):
        self.db = db_func
    
    async def calculate_mrr(self) -> Decimal:
        """Calculate Monthly Recurring Revenue."""
        rows = await self.db(
            """
            SELECT SUM(
                CASE 
                    WHEN subscription_tier = 'free' THEN 0
                    WHEN subscription_tier = 'starter' THEN 99.00
                    WHEN subscription_tier = 'pro' THEN 299.00
                    ELSE 0
                END
            ) as mrr
            FROM users
            WHERE subscription_tier != 'free'
            """,
            (),
            fetchone=True
        )
        
        return Decimal(str(rows["mrr"] or 0))
    
    async def calculate_arr(self) -> Decimal:
        """Calculate Annual Recurring Revenue."""
        mrr = await self.calculate_mrr()
        return mrr * 12
    
    async def calculate_churn_rate(self, days: int = 30) -> float:
        """Calculate churn rate (% of customers lost)."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Customers at start of period
        row1 = await self.db(
            """
            SELECT COUNT(*) as total
            FROM users
            WHERE subscription_tier != 'free'
            AND created_at <= ?
            """,
            (cutoff,),
            fetchone=True
        )
        
        # Churned during period
        row2 = await self.db(
            """
            SELECT COUNT(*) as churned
            FROM users
            WHERE subscription_tier = 'free'
            AND subscription_tier != 'free' -- was paid
            AND subscription_updated_at BETWEEN ? AND ?
            """,
            (cutoff, datetime.utcnow().isoformat()),
            fetchone=True
        )
        
        total = row1["total"] or 1
        churned = row2["churned"] or 0
        
        return (churned / total) * 100 if total > 0 else 0

# ─────── DATABASE SCHEMA ─────────
BILLING_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    stripe_customer_id TEXT UNIQUE,
    subscription_tier TEXT DEFAULT 'free',
    subscription_period_start TEXT,
    subscription_period_end TEXT,
    subscription_updated_at TEXT,
    renewal_reminder_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    metric TEXT,  -- leads_sent, emails_sent, calls_made, etc.
    quantity INTEGER,
    logged_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    invoice_id TEXT UNIQUE,
    period_start TEXT,
    period_end TEXT,
    subtotal DECIMAL(10,2),
    overage_charges DECIMAL(10,2),
    total DECIMAL(10,2),
    status TEXT DEFAULT 'draft',
    paid_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_users_tier ON users(subscription_tier);
CREATE INDEX IF NOT EXISTS idx_usage_client ON usage_log(client_id);
CREATE INDEX IF NOT EXISTS idx_invoices_client ON invoices(client_id);
"""

# ─────── SINGLETON INSTANCES ─────────
stripe_manager = StripePaymentManager()
metered_billing = MeteredBillingManager(None)  # Injected at runtime
subscription_manager = SubscriptionManager(stripe_manager, None)  # Injected at runtime
revenue_analytics = RevenueAnalytics(None)  # Injected at runtime
