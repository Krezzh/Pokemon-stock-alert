# Pokémon 30th Anniversary NZ Stock Alert

This GitHub Actions bot checks selected New Zealand Pokémon 30th Anniversary product pages about every 5 minutes and sends a Telegram message when a product changes to available.

## Setup

1. Create a GitHub repository and upload all files in this folder.
2. In GitHub go to:
   **Settings → Secrets and variables → Actions → New repository secret**
3. Create a secret named:
   `TELEGRAM_BOT_TOKEN`
4. Paste your new Telegram bot token into that secret. **Never put the token in the code or commit it.**
5. Open **Actions**, select **Pokémon 30th Stock Checker**, and use **Run workflow** once to test it.

The Telegram chat ID is already set to the user's chat ID in the workflow.

## Important

GitHub's 5-minute schedule is approximate; scheduled jobs can sometimes be delayed by GitHub during busy periods.

The initial product list can be expanded with more NZ retailers and product URLs.
