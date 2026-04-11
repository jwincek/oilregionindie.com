"""
Stripe Connect integration for the Oil Region Creative Hub.

This module handles all Stripe interactions:
- Onboarding creators/venues to Stripe Connect (Express accounts)
- Creating Checkout Sessions for product purchases
- Processing webhooks for payment confirmation
"""

import logging

import stripe
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_connect_account(creator_or_venue):
    """
    Create a Stripe Express connected account for a creator or venue.
    Returns the Stripe account ID.
    """
    account = stripe.Account.create(
        type="express",
        capabilities={
            "card_payments": {"requested": True},
            "transfers": {"requested": True},
        },
        metadata={
            "platform": "oilregion_hub",
            "profile_id": str(creator_or_venue.id),
        },
    )
    return account.id


def create_onboarding_link(account_id, return_url, refresh_url):
    """
    Create a Stripe-hosted onboarding link for a connected account.
    The creator/venue completes setup on Stripe's site, then returns.
    """
    link = stripe.AccountLink.create(
        account=account_id,
        return_url=return_url,
        refresh_url=refresh_url,
        type="account_onboarding",
    )
    return link.url


def check_account_status(account_id):
    """Check whether a connected account has completed onboarding."""
    account = stripe.Account.retrieve(account_id)
    return {
        "charges_enabled": account.charges_enabled,
        "payouts_enabled": account.payouts_enabled,
        "details_submitted": account.details_submitted,
    }


def create_checkout_session(product, quantity, success_url, cancel_url, buyer_email=None):
    """
    Create a Stripe Checkout Session for purchasing a product.
    Money goes directly to the creator's connected account.
    """
    creator = product.creator

    if not creator.can_accept_payments:
        raise ValueError("Creator has not completed Stripe onboarding")

    # Calculate platform fee
    fee_percent = settings.STRIPE_PLATFORM_FEE_PERCENT
    unit_amount = product.price_cents
    platform_fee = int(unit_amount * quantity * fee_percent / 100) if fee_percent else 0

    session_params = {
        "mode": "payment",
        "line_items": [
            {
                "price_data": {
                    "currency": product.currency.lower(),
                    "unit_amount": unit_amount,
                    "product_data": {
                        "name": product.title,
                        "description": product.get_product_type_display(),
                        "metadata": {
                            "product_id": str(product.id),
                            "creator_id": str(creator.id),
                        },
                    },
                },
                "quantity": quantity,
            }
        ],
        "payment_intent_data": {
            "application_fee_amount": platform_fee,
            "transfer_data": {
                "destination": creator.stripe_account_id,
            },
            "metadata": {
                "product_id": str(product.id),
                "creator_id": str(creator.id),
            },
        },
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {
            "product_id": str(product.id),
            "creator_id": str(creator.id),
        },
    }

    if buyer_email:
        session_params["customer_email"] = buyer_email

    # For physical products, collect shipping address
    if not product.is_digital:
        session_params["shipping_address_collection"] = {
            "allowed_countries": ["US"],
        }

    session = stripe.checkout.Session.create(**session_params)
    return session


def construct_webhook_event(payload, sig_header):
    """Verify and construct a Stripe webhook event."""
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )


def create_login_link(account_id):
    """Create a link to the Stripe Express dashboard for a connected account."""
    link = stripe.Account.create_login_link(account_id)
    return link.url
