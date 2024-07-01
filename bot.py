import discord
from discord.ext import commands
import random
from config import TOKEN

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='>>', intents=intents)

games = {}

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Bot connected as {bot.user}')

@bot.command(name='ping')
async def ping(ctx):
    latency = bot.latency * 1000  # Convert to milliseconds
    await ctx.send(f'Pong! {latency:.2f} ms')

@bot.command(name='hostgame')
async def host_game(ctx):
    game_id = ctx.guild.id
    if game_id in games:
        await ctx.send("A game is already in progress.")
        return

    games[game_id] = {
        'host': ctx.author,
        'players': [],
        'assigned_players': [],
        'phase': 'setup',
        'votes': {},
        'hints': [],
        'hint_queue': [],
        'all_hints': [],  # List to store all hints
        'round': 1,  # To track the number of hint rounds
    }

    await ctx.send(f"{ctx.author.display_name} is now hosting a game. Players can join using >>join.")

@bot.command(name='join')
async def join_game(ctx):
    game_id = ctx.guild.id
    if game_id not in games:
        await ctx.send("No game is being hosted.")
        return

    game = games[game_id]
    if ctx.author in game['players']:
        await ctx.send("You are already in the game.")
        return

    if game['phase'] != 'setup':
        await ctx.send("The game has already started. You can't join now.")
        return

    game['players'].append(ctx.author)
    await ctx.send(f"{ctx.author.display_name} has joined the game. Current players: {', '.join([player.display_name for player in game['players']])}")

@bot.command(name='leave')
async def leave_game(ctx):
    game_id = ctx.guild.id
    if game_id not in games:
        await ctx.send("No game is being hosted.")
        return

    game = games[game_id]
    if ctx.author not in game['players']:
        await ctx.send("You are not in the current game.")
        return

    game['players'].remove(ctx.author)
    await ctx.send(f"{ctx.author.display_name} has left the game. Current players: {', '.join([player.display_name for player in game['players']])}")

    if len(game['players']) == 0:
        del games[game_id]
        await ctx.send("No players left in the game. The game has been canceled.")

@bot.command(name='startgame')
async def start_game(ctx):
    game_id = ctx.guild.id
    if game_id not in games:
        await ctx.send("No game is being hosted.")
        return

    game = games[game_id]
    if ctx.author != game['host']:
        await ctx.send("Only the host can start the game.")
        return

    if game['phase'] != 'ready':
        await ctx.send("The game is not ready to start. Make sure the host has set the players.")
        return

    players = game['players']

    # DM the host with player assignments
    assigned_message = '\n'.join(f"{player.display_name} - {assignment}" for player, assignment in game['assigned_players'])
    await ctx.author.send(f"Players and their assignments:\n{assigned_message}")

    # Determine the number of impostors based on the number of players
    num_impostors = 1
    if len(players) > 6:
        num_impostors = 2
    if len(players) > 8:
        num_impostors = 3

    # Ensure at least one player gets a different item
    random.shuffle(players)
    player_assignments = game['assigned_players']
    random.shuffle(player_assignments)

    for player, assignment in player_assignments:
        try:
            await player.send(f"The item you got is: {assignment}.")
        except discord.HTTPException:
            await ctx.send(f"Could not send a DM to {player.display_name}. Please ensure your DMs are enabled for server members.")

    game['phase'] = 'playing'
    game['impostors'] = num_impostors
    game['crewmates'] = len(players) - num_impostors
    game['hint_queue'] = random.sample(players, len(players))
    await ctx.send(f"Game started with {len(players)} players. Use >>hint to give hints and >>vote @player to vote for the impostor. Hint order: {', '.join([player.display_name for player in game['hint_queue']])}")

@bot.command(name='hint')
async def give_hint(ctx, *, hint: str):
    game_id = ctx.guild.id
    if game_id not in games:
        await ctx.send("No game in progress.")
        return

    game = games[game_id]
    if ctx.author not in game['players']:
        await ctx.send("You are not in the current game.")
        return

    if game['phase'] != 'playing':
        await ctx.send("Hints can only be given during the playing phase.")
        return

    if game['hint_queue'] and game['hint_queue'][0] != ctx.author:
        await ctx.send(f"It is not your turn to give a hint. Next up: {game['hint_queue'][0].display_name}")
        return

    game['hints'].append((ctx.author, hint))
    game['all_hints'].append((ctx.author.display_name, hint))  # Store hint with author in the all_hints list
    print(f"{ctx.author.display_name} gave a hint: {hint}")  # Print hint to the terminal
    game['hint_queue'].pop(0)

    if game['hint_queue']:
        await ctx.send(f"Hint recorded from {ctx.author.display_name}. Next up: {game['hint_queue'][0].display_name}")
    else:
        # Check the number of players and impostors to decide the next action
        if len(game['players']) < 5 or game['impostors'] > 1:
            if game['round'] < 3:
                game['round'] += 1
                game['hint_queue'] = random.sample(game['players'], len(game['players']))
                await ctx.send(f"Round {game['round']} of hint giving starts now. Hint order: {', '.join([player.display_name for player in game['hint_queue']])}")
            else:
                await ctx.send(f"All hints are in. Proceed to voting.")
                game['phase'] = 'voting'
        else:
            await ctx.send(f"All hints are in. Proceed to voting.")
            game['phase'] = 'voting'

@bot.command(name='showhints')
async def show_hints(ctx):
    game_id = ctx.guild.id
    if game_id not in games:
        await ctx.send("No game in progress.")
        return

    game = games[game_id]
    if not game['all_hints']:
        await ctx.send("No hints have been given yet.")
        return

    hints_message = '\n'.join([f"{author}: {hint}" for author, hint in game['all_hints']])
    await ctx.send(f"All given hints:\n{hints_message}")

@bot.command(name='vote')
async def vote_player(ctx, player: discord.Member):
    game_id = ctx.guild.id
    if game_id not in games:
        await ctx.send("No game in progress.")
        return

    game = games[game_id]
    if game['phase'] != 'voting':
        await ctx.send("It is not the voting phase.")
        return

    if ctx.author not in game['players']:
        await ctx.send("You are not in the current game.")
        return

    if player not in game['players']:
        await ctx.send("The specified player is not in the current game.")
        return

    if ctx.author in game['votes']:
        await ctx.send("You have already voted.")
        return

    if player not in game['votes']:
        game['votes'][player] = []

    game['votes'][player].append(ctx.author)
    await ctx.send(f"{ctx.author.display_name} voted for {player.display_name}.")

    if len(game['votes']) == len(game['players']):
        await evaluate_votes(ctx)

async def evaluate_votes(ctx):
    game_id = ctx.guild.id
    game = games[game_id]

    # Find the impostor
    impostor = [player for player, assignment in game['assigned_players'] if assignment == game['assigned_players'][1][1]][0]
    
    # Determine who got the most votes
    max_votes = max(len(voters) for voters in game['votes'].values())
    most_voted_players = [player for player, voters in game['votes'].items() if len(voters) == max_votes]

    if len(most_voted_players) == 1:
        most_voted_player = most_voted_players[0]
        if most_voted_player == impostor:
            await ctx.send(f"{most_voted_player.display_name} was the impostor. Crewmates win!")
            del games[game_id]
        else:
            game['crewmates'] -= 1
            await ctx.send(f"{most_voted_player.display_name} was not the impostor. They have been eliminated.")
            game['players'].remove(most_voted_player)
            game['hint_queue'] = random.sample(game['players'], len(game['players']))

            if len(game['players']) <= 3 or game['impostors'] >= game['crewmates']:
                await ctx.send("Impostor wins! Game over.")
                del games[game_id]
            else:
                await ctx.send(f"Continuing game with {game['crewmates']} crewmates left. Next hint order: {', '.join([player.display_name for player in game['hint_queue']])}")
                game['phase'] = 'playing'
    else:
        await ctx.send("No consensus was reached. The game continues.")
        game['hint_queue'] = random.sample(game['players'], len(game['players']))
        await ctx.send(f"Next hint order: {', '.join([player.display_name for player in game['hint_queue']])}")

@bot.command(name='kick')
async def kick_player(ctx, player: discord.Member):
    game_id = ctx.guild.id
    if game_id not in games:
        await ctx.send("No game in progress.")
        return

    game = games[game_id]
    if ctx.author != game['host']:
        await ctx.send("Only the host can kick players.")
        return

    if player not in game['players']:
        await ctx.send("The specified player is not in the current game.")
        return

    game['players'].remove(player)
    await ctx.send(f"{player.display_name} has been kicked from the game. Current players: {', '.join([player.display_name for player in game['players']])}")

    if len(game['players']) == 0:
        del games[game_id]
        await ctx.send("No players left in the game. The game has been canceled.")
    else:
        game['hint_queue'] = random.sample(game['players'], len(game['players']))
        await ctx.send(f"Updated hint order: {', '.join([player.display_name for player in game['hint_queue']])}")

@bot.command(name='endgame')
async def end_game(ctx):
    game_id = ctx.guild.id
    if game_id not in games:
        await ctx.send("No game is being hosted.")
        return

    game = games[game_id]
    if ctx.author != game['host']:
        await ctx.send("Only the host can end the game.")
        return

    del games[game_id]
    await ctx.send("The game has been ended by the host.")

class SetPlayers(discord.app_commands.Group, name="setplayers"):
    @discord.app_commands.command(name="set")
    async def set(self, interaction: discord.Interaction, items1: str, items2: str):
        game_id = interaction.guild.id
        if game_id not in games:
            await interaction.response.send_message("No game is being hosted.", ephemeral=True)
            return

        game = games[game_id]
        if interaction.user != game['host']:
            await interaction.response.send_message("Only the host can set the players.", ephemeral=True)
            return

        item_list = [items1, items2]

        # Assign items to players
        assignments = []
        impostor = random.choice(game['players'])
        for player in game['players']:
            if player == impostor:
                assignments.append((player, items2))
            else:
                assignments.append((player, items1))

        game['assigned_players'] = assignments
        game['phase'] = 'ready'
        await interaction.response.send_message("Players have been set. The game is now ready to start.", ephemeral=True)

        # DM the host with player assignments
        assigned_message = '\n'.join(f"{player.display_name} - {assignment}" for player, assignment in game['assigned_players'])
        await interaction.user.send(f"Players and their assignments:\n{assigned_message}")

bot.tree.add_command(SetPlayers())

bot.run(TOKEN)
