# Facebook Messenger AI Sales Bot — Setup

This integration adds a webhook at `/webhook/messenger` to the existing Fashion Mart Node/Express service. It reads the live products from the existing PostgreSQL catalogue and drafts Bengali replies with OpenAI. Special-discount requests are never approved automatically; when Telegram notification variables are configured, the owner receives an approval request.

## Required Render environment variables

Set these on the **fashion-mart-secure** web service:

- `META_VERIFY_TOKEN`: a long random string you create; enter the same value in Meta webhook configuration.
- `META_APP_SECRET`: App Secret from Meta for Developers (keep secret).
- `META_PAGE_ACCESS_TOKEN`: Page access token with the required Messenger permissions.
- `OPENAI_API_KEY`: API key for AI-generated replies.

Optional:
- `OPENAI_MODEL`: defaults to `gpt-4o-mini`.
- `META_GRAPH_VERSION`: defaults to `v23.0`; update when needed to a currently supported version.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`: optional owner notifications for discount approvals, complaints, refunds, exchanges and wholesale requests.

Do not put tokens in source files or send them in chat.

## Meta setup prerequisites

A person with **Facebook Page full control / appropriate admin access** must authorize the Page and complete Meta app setup. Moderator-only access is not enough to independently create/authorize all required app subscriptions and Page access tokens. Ask the Page owner to grant the appropriate access or have them complete these steps.

1. Open Meta for Developers and create/select an app with the Messenger product.
2. Connect the correct Facebook Page and generate a Page access token with the required messaging permissions.
3. Configure the webhook callback URL as `https://fashion-mart-secure.onrender.com/webhook/messenger`.
4. Use the exact `META_VERIFY_TOKEN` value as the webhook verification token.
5. Subscribe the app to the Page's `messages` webhook field and complete any Meta app review/business verification requirements that apply before production use.
6. Add all required Render environment variables and redeploy the `fashion-mart-secure` service.
7. Test with a permitted tester account first; confirm the webhook verifies, incoming messages receive replies, product details match the database catalogue, and discount requests notify the owner.

## Important behavior and limits

- Product facts come from the shared `products` table; add/update products through the existing admin panel.
- The bot must not invent prices, sizes, stock, shipping details or offers.
- Special discounts are approval-only. The bot notifies the owner through Telegram only if both optional Telegram variables are configured.
- Order placement is not implemented through Messenger in this first integration. The bot must not claim an order has been placed; use the existing storefront checkout for real orders.
- This is a code integration, not proof of a successful Meta connection. It will not answer customers until the owner completes Meta authorization, Render variables are configured, and the deployment is live.
