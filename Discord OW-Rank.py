import discord
from discord.ext import commands
import aiohttp
import asyncio
import json
from typing import Optional

# Bot configuration - enable message content intent for regular commands
intents = discord.Intents.default()
intents.message_content = True  # Required for !commands to work
bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is ready to fetch Overwatch ranks!')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


async def fetch_player_data(battletag: str) -> Optional[dict]:
    """
    Fetch player data from multiple API sources with different format attempts
    battletag format: PlayerName-1234
    """
    try:
        # Create different variations of the BattleTag to try
        original_tag = battletag
        dash_tag = battletag.replace('#', '-')
        hash_tag = battletag.replace('-', '#')

        # URL encode for special characters
        import urllib.parse
        encoded_dash = urllib.parse.quote(dash_tag, safe='')
        encoded_hash = urllib.parse.quote(hash_tag, safe='')

        battletags_to_try = [dash_tag, encoded_dash, hash_tag, encoded_hash]

        async with aiohttp.ClientSession() as session:

            # Try each BattleTag variation with OverFast API
            for i, tag in enumerate(battletags_to_try):
                url = f"https://overfast-api.tekrop.fr/players/{tag}/summary"
                print(f"Trying OverFast API (attempt {i + 1}): {url}")

                async with session.get(url) as response:
                    print(f"OverFast API Response Status: {response.status}")
                    if response.status == 200:
                        try:
                            data = await response.json()
                            print(f"OverFast API Success with tag format: {tag}")
                            return data
                        except Exception as e:
                            print(f"Failed to parse JSON from OverFast API: {e}")
                    elif response.status == 404:
                        print(f"Player not found with tag format: {tag}")
                    else:
                        print(f"OverFast API Error: {response.status}")
                        try:
                            response_text = await response.text()
                            print(f"Error response: {response_text[:200]}...")
                        except:
                            print("Could not read error response")

            # Try alternative API - ow-api.com with different formats
            for i, tag in enumerate([dash_tag, encoded_dash]):
                alt_url = f"https://ow-api.com/v1/stats/pc/global/{tag}/complete"
                print(f"Trying alternative API (attempt {i + 1}): {alt_url}")

                async with session.get(alt_url) as response:
                    print(f"Alternative API Response Status: {response.status}")
                    if response.status == 200:
                        try:
                            data = await response.json()
                            print(f"Alternative API Success with tag format: {tag}")
                            return {"alternative_api": True, "data": data}
                        except Exception as e:
                            print(f"Failed to parse JSON from alternative API: {e}")
                    else:
                        print(f"Alternative API Error: {response.status}")
                        try:
                            response_text = await response.text()
                            print(f"Alt API Error response: {response_text[:200]}...")
                        except:
                            print("Could not read alt API error response")

            print("All API attempts failed")
            return None

    except Exception as e:
        print(f"Error fetching player data: {e}")
        import traceback
        traceback.print_exc()
        return None


def format_rank_info(data: dict) -> str:
    """Format competitive rank information from various API sources"""
    if not data:
        return "❌ No competitive data found for this player."

    # Handle OverFast API format
    if 'competitive' in data:
        competitive_data = data.get('competitive', {})
        pc_comp = competitive_data.get('pc', {})

        if not pc_comp:
            return "❌ No PC competitive data found for this player."

        rank_info = []

        # Tank role
        if 'tank' in pc_comp and pc_comp['tank']:
            tank = pc_comp['tank']
            rank_info.append(f"🛡️ **Tank**: {tank.get('division', 'Unranked')} - {tank.get('tier', 0)} SR")

        # Damage role
        if 'damage' in pc_comp and pc_comp['damage']:
            damage = pc_comp['damage']
            rank_info.append(f"⚔️ **Damage**: {damage.get('division', 'Unranked')} - {damage.get('tier', 0)} SR")

        # Support role
        if 'support' in pc_comp and pc_comp['support']:
            support = pc_comp['support']
            rank_info.append(f"💚 **Support**: {support.get('division', 'Unranked')} - {support.get('tier', 0)} SR")

        if not rank_info:
            return "❌ No competitive ranks found. Player may be unranked or have private profile."

        return "\n".join(rank_info)

    # Handle alternative API format (ow-api.com)
    elif 'alternative_api' in data and data['alternative_api']:
        alt_data = data.get('data', {})

        if 'error' in alt_data:
            return f"❌ API Error: {alt_data['error']}"

        if 'competitiveStats' in alt_data and 'games' in alt_data['competitiveStats']:
            games = alt_data['competitiveStats']['games']

            rank_info = []

            # Check for competitive data
            if 'competitive' in games:
                comp_data = games['competitive']

                # Overall competitive info
                if 'overall_stats' in comp_data:
                    overall = comp_data['overall_stats']
                    if 'comprank' in overall:
                        rank_info.append(f"🏆 **Overall Rank**: {overall['comprank']} SR")
                    if 'tier' in overall:
                        rank_info.append(f"📊 **Tier**: {overall['tier']}")

                if rank_info:
                    return "\n".join(rank_info)

        # Try to get any available competitive info
        if 'rating' in alt_data:
            return f"🏆 **Rating**: {alt_data['rating']}"

        return "❌ No competitive data available from alternative API."

    return "❌ Unknown data format received."


@bot.command(name='rank')
async def get_rank(ctx, *, battletag: str = None):
    """
    Get Overwatch competitive rank for a player
    Usage: !rank PlayerName-1234
    """
    if not battletag:
        await ctx.send("❌ Please provide a BattleTag! Usage: `!rank PlayerName-1234`")
        return

    # Send initial message
    message = await ctx.send(f"🔍 Looking up Overwatch rank for **{battletag}**...")

    try:
        # Fetch player data
        player_data = await fetch_player_data(battletag)

        if player_data is None:
            await message.edit(
                content="❌ Player not found! Make sure the BattleTag is correct (format: PlayerName-1234) and profile is set to PUBLIC in Overwatch 2 settings.")
            return

        # Create embed for better formatting
        embed = discord.Embed(
            title=f"🎮 Overwatch Rank - {battletag}",
            color=discord.Color.orange()
        )

        # Handle different API data formats
        if player_data.get('alternative_api'):
            # Alternative API data (ow-api.com)
            alt_data = player_data.get('data', {})

            if 'name' in alt_data:
                embed.add_field(name="Player", value=alt_data['name'], inline=True)

            if 'level' in alt_data:
                embed.add_field(name="Level", value=str(alt_data['level']), inline=True)

            if 'prestige' in alt_data:
                embed.add_field(name="Prestige", value=str(alt_data['prestige']), inline=True)

            # Add rank information
            rank_text = format_rank_info(player_data)
            embed.add_field(name="Competitive Info", value=rank_text, inline=False)

            if 'endorsement' in alt_data:
                embed.add_field(name="Endorsement Level", value=str(alt_data['endorsement']), inline=True)

            if 'portrait' in alt_data:
                embed.set_thumbnail(url=alt_data['portrait'])

            embed.set_footer(text="Data provided by ow-api.com")

        else:
            # OverFast API data (original format)
            if 'username' in player_data:
                embed.add_field(name="Player", value=player_data['username'], inline=True)

            if 'title' in player_data and player_data['title']:
                embed.add_field(name="Title", value=player_data['title'], inline=True)

            # Add rank information
            rank_text = format_rank_info(player_data)
            embed.add_field(name="Current Competitive Ranks", value=rank_text, inline=False)

            if 'level' in player_data:
                embed.add_field(name="Level", value=str(player_data['level']), inline=True)

            if 'endorsement' in player_data and 'level' in player_data['endorsement']:
                embed.add_field(name="Endorsement Level", value=str(player_data['endorsement']['level']), inline=True)

            if 'avatar' in player_data and player_data['avatar']:
                embed.set_thumbnail(url=player_data['avatar'])

            embed.set_footer(text="Data provided by OverFast API")

        await message.edit(content="", embed=embed)

    except Exception as e:
        await message.edit(content=f"❌ An error occurred while fetching rank data: {str(e)}")
        print(f"Error in get_rank command: {e}")
        import traceback
        traceback.print_exc()


# Add slash command version
@bot.tree.command(name="rank", description="Get Overwatch competitive rank for a player")
async def rank_slash(interaction: discord.Interaction, battletag: str):
    """Slash command version of rank lookup"""
    await interaction.response.defer()

    try:
        # Fetch player data
        player_data = await fetch_player_data(battletag)

        if player_data is None:
            await interaction.followup.send(
                "❌ Player not found! Make sure the BattleTag is correct (format: PlayerName-1234) and profile is set to PUBLIC in Overwatch 2 settings.")
            return

        # Create embed for better formatting
        embed = discord.Embed(
            title=f"🎮 Overwatch Rank - {battletag}",
            color=discord.Color.orange()
        )

        # Handle different API data formats
        if player_data.get('alternative_api'):
            # Alternative API data (ow-api.com)
            alt_data = player_data.get('data', {})

            if 'name' in alt_data:
                embed.add_field(name="Player", value=alt_data['name'], inline=True)

            if 'level' in alt_data:
                embed.add_field(name="Level", value=str(alt_data['level']), inline=True)

            if 'prestige' in alt_data:
                embed.add_field(name="Prestige", value=str(alt_data['prestige']), inline=True)

            # Add rank information
            rank_text = format_rank_info(player_data)
            embed.add_field(name="Competitive Info", value=rank_text, inline=False)

            if 'endorsement' in alt_data:
                embed.add_field(name="Endorsement Level", value=str(alt_data['endorsement']), inline=True)

            if 'portrait' in alt_data:
                embed.set_thumbnail(url=alt_data['portrait'])

            embed.set_footer(text="Data provided by ow-api.com")

        else:
            # OverFast API data (original format)
            if 'username' in player_data:
                embed.add_field(name="Player", value=player_data['username'], inline=True)

            if 'title' in player_data and player_data['title']:
                embed.add_field(name="Title", value=player_data['title'], inline=True)

            # Add rank information
            rank_text = format_rank_info(player_data)
            embed.add_field(name="Current Competitive Ranks", value=rank_text, inline=False)

            if 'level' in player_data:
                embed.add_field(name="Level", value=str(player_data['level']), inline=True)

            if 'endorsement' in player_data and 'level' in player_data['endorsement']:
                embed.add_field(name="Endorsement Level", value=str(player_data['endorsement']['level']), inline=True)

            if 'avatar' in player_data and player_data['avatar']:
                embed.set_thumbnail(url=player_data['avatar'])

            embed.set_footer(text="Data provided by OverFast API")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred while fetching rank data: {str(e)}")
        print(f"Error in rank_slash command: {e}")


# Add diagnostic command
@bot.command(name='test_api')
async def test_api(ctx):
    """Test API endpoints to diagnose issues"""
    embed = discord.Embed(
        title="🔧 API Diagnostic Test",
        description="Testing different API endpoints...",
        color=discord.Color.blue()
    )

    message = await ctx.send(embed=embed)

    async with aiohttp.ClientSession() as session:
        # Test 1: Check if OverFast API is responding at all
        try:
            async with session.get("https://overfast-api.tekrop.fr/") as response:
                status1 = f"✅ Status {response.status}" if response.status == 200 else f"❌ Status {response.status}"
                embed.add_field(name="1. OverFast API Home", value=status1, inline=False)
        except Exception as e:
            embed.add_field(name="1. OverFast API Home", value=f"❌ Error: {str(e)}", inline=False)

        # Test 2: Try a known working player (if any)
        test_players = ["Seagull-12496", "xQc-11819", "Surefour-11271", "KarQ-11770"]

        for i, player in enumerate(test_players):
            try:
                url = f"https://overfast-api.tekrop.fr/players/{player}/summary"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        embed.add_field(name=f"2.{i + 1} Test Player: {player}",
                                        value=f"✅ Found! Username: {data.get('username', 'N/A')}", inline=False)
                        break
                    else:
                        embed.add_field(name=f"2.{i + 1} Test Player: {player}",
                                        value=f"❌ Status {response.status}", inline=False)
            except Exception as e:
                embed.add_field(name=f"2.{i + 1} Test Player: {player}",
                                value=f"❌ Error: {str(e)}", inline=False)

        # Test 3: Check alternative API
        try:
            async with session.get("https://ow-api.com/") as response:
                status3 = f"✅ Status {response.status}" if response.status == 200 else f"❌ Status {response.status}"
                embed.add_field(name="3. Alternative API (ow-api.com)", value=status3, inline=False)
        except Exception as e:
            embed.add_field(name="3. Alternative API (ow-api.com)", value=f"❌ Error: {str(e)}", inline=False)

        # Test 4: Try to get heroes data (should always work)
        try:
            async with session.get("https://overfast-api.tekrop.fr/heroes") as response:
                if response.status == 200:
                    heroes = await response.json()
                    embed.add_field(name="4. Heroes Endpoint",
                                    value=f"✅ Working! Found {len(heroes)} heroes", inline=False)
                else:
                    embed.add_field(name="4. Heroes Endpoint",
                                    value=f"❌ Status {response.status}", inline=False)
        except Exception as e:
            embed.add_field(name="4. Heroes Endpoint", value=f"❌ Error: {str(e)}", inline=False)

    embed.color = discord.Color.green()
    embed.description = "API diagnostic complete!"
    await message.edit(embed=embed)


# Add command to check if Blizzard's official search works
@bot.command(name='check_profile')
async def check_profile(ctx, *, battletag: str = None):
    """Check if a profile is publicly visible on Blizzard's official site"""
    if not battletag:
        await ctx.send("❌ Please provide a BattleTag! Usage: `!check_profile PlayerName-1234`")
        return

    battletag = battletag.replace('#', '-')

    embed = discord.Embed(
        title=f"🔍 Profile Visibility Check",
        description=f"Checking if **{battletag}** is publicly visible...",
        color=discord.Color.blue()
    )

    message = await ctx.send(embed=embed)

    try:
        async with aiohttp.ClientSession() as session:
            # Try to access Blizzard's official player search
            blizzard_url = f"https://overwatch.blizzard.com/en-us/search/{battletag}/"

            async with session.get(blizzard_url) as response:
                if response.status == 200:
                    content = await response.text()
                    # Simple check for profile content
                    if "profile" in content.lower() and "competitive" in content.lower():
                        embed.add_field(name="✅ Profile Status",
                                        value="Profile appears to be public on Blizzard's site",
                                        inline=False)
                        embed.color = discord.Color.green()
                    else:
                        embed.add_field(name="❌ Profile Status",
                                        value="Profile may be private or doesn't exist",
                                        inline=False)
                        embed.color = discord.Color.red()
                else:
                    embed.add_field(name="❌ Profile Status",
                                    value=f"Blizzard search returned status {response.status}",
                                    inline=False)
                    embed.color = discord.Color.red()

        # Add instructions
        embed.add_field(name="📝 How to make your profile public:",
                        value="""1. Open Overwatch 2
2. Go to Settings → Social (or Options → Social)
3. Set **Career Profile Visibility** to **Public**  
4. **Restart Overwatch 2 completely**
5. Wait a few minutes for changes to take effect""",
                        inline=False)

        embed.add_field(name="🔗 Official Search",
                        value=f"[Check on Blizzard's site](https://overwatch.blizzard.com/en-us/search/)",
                        inline=False)

    except Exception as e:
        embed.add_field(name="❌ Error", value=f"Could not check profile: {str(e)}", inline=False)
        embed.color = discord.Color.red()

    embed.description = f"Profile check complete for **{battletag}**"
    await message.edit(embed=embed)


@bot.command(name='help_overwatch')
async def help_overwatch(ctx):
    """Show help for Overwatch commands"""
    embed = discord.Embed(
        title="🎮 Overwatch Bot Commands",
        description="Commands for checking Overwatch player information",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="!rank <BattleTag>",
        value="Get competitive rank for a player\nExample: `!rank PlayerName-1234`",
        inline=False
    )

    embed.add_field(
        name="/rank <BattleTag>",
        value="Slash command version of rank lookup\nExample: `/rank PlayerName-1234`",
        inline=False
    )

    embed.add_field(
        name="!check_profile <BattleTag>",
        value="Check if a profile is publicly visible\nExample: `!check_profile PlayerName-1234`",
        inline=False
    )

    embed.add_field(
        name="!test_api",
        value="Run diagnostic tests on API endpoints\nExample: `!test_api`",
        inline=False
    )

    embed.add_field(
        name="BattleTag Format",
        value="Use the format: `PlayerName-1234`\nYou can use either `-` or `#` between name and numbers",
        inline=False
    )

    embed.add_field(
        name="📋 Important Notes",
        value="""• Player profiles must be set to **PUBLIC** in Overwatch 2 settings
• Go to: Settings → Social → Career Profile Visibility → Public  
• **Restart Overwatch 2** after changing settings
• Wait a few minutes for changes to take effect
• Most profiles are private by default in Overwatch 2""",
        inline=False
    )

    await ctx.send(embed=embed)


@get_rank.error
async def rank_error(ctx, error):
    """Handle errors for the rank command"""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Please provide a BattleTag! Usage: `!rank PlayerName-1234`")
    else:
        await ctx.send("❌ An error occurred. Please try again later.")
        print(f"Command error: {error}")


# Run the bot
if __name__ == "__main__":
    # Get bot token from environment variable
    import os
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    
    if not TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN environment variable not found!")
        print("Please set your Discord bot token as an environment variable:")
        print("Windows: set DISCORD_BOT_TOKEN=your_token_here")
        print("Linux/Mac: export DISCORD_BOT_TOKEN=your_token_here")
        exit(1)

    print("Starting Overwatch Discord Bot...")
    print("Commands available:")
    print("  !rank <BattleTag> - Get competitive rank")
    print("  /rank <BattleTag> - Slash command version")
    print("  !check_profile <BattleTag> - Check profile visibility")
    print("  !test_api - Test API endpoints")
    print("  !help_overwatch - Show help")
    print("\nMake sure to:")
    print("1. Set DISCORD_BOT_TOKEN environment variable with your bot token")
    print("2. Install required packages: pip install discord.py aiohttp")

    # Run the bot with the token from environment variable
    bot.run(TOKEN)
