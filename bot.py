import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from typing import Dict, List
import asyncio
import logging
import threading

# Update logging configuration at the top of the file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('stock_bot')

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Bot setup with minimal required intents
intents = discord.Intents.default()
intents.message_content = True  # We need message content for commands
intents.guilds = True  # We only need guild/server information
bot = commands.Bot(command_prefix='!', intents=intents)

# Modified stock data structure to store detailed information
stock_data = {
    'pp_logs': [],  # Will store dicts with email and password
    'ccs': []       # Will store dicts with cc number, expiry, and cvc
}

# Channel ID for setup command
SETUP_CHANNEL_ID = None

# Role IDs - These will be set during setup
ROLES = {
    'owner': None,
    'manager': None,
    'member': None
}

def check_permissions(member: discord.Member, required_role: str) -> bool:
    """Check if a member has the required role or higher"""
    if not all(ROLES.values()):  # If roles aren't set up yet
        logger.warning(f"Roles not set up when checking permissions. Current ROLES: {ROLES}")
        return False

    user_role_ids = [role.id for role in member.roles]
    logger.info(f"Checking permissions for {member.name} ({member.id}) - Has roles: {user_role_ids}")
    logger.info(f"Required role: {required_role}, Available roles: {ROLES}")

    # Server owner always has all permissions
    if member.guild.owner_id == member.id:
        logger.info(f"User {member.name} is server owner, granting all permissions")
        return True

    # Check based on role hierarchy
    if required_role == 'member':
        has_permission = any(role_id in user_role_ids for role_id in ROLES.values())
        logger.info(f"Member permission check result: {has_permission}")
        return has_permission
    elif required_role == 'manager':
        has_permission = any(role_id in user_role_ids for role_id in [ROLES['manager'], ROLES['owner']])
        logger.info(f"Manager permission check result: {has_permission}")
        return has_permission
    elif required_role == 'owner':
        has_permission = ROLES['owner'] in user_role_ids
        logger.info(f"Owner permission check result: {has_permission}")
        return has_permission
    return False

# Add debug logging for stock operations
def log_stock_operation(operation: str, stock_type: str, quantity: int, user: str):
    """Helper function to log stock operations consistently"""
    current_stock = len(stock_data[stock_type])
    logger.info(f"Stock Operation: {operation} | Type: {stock_type} | Quantity: {quantity} | "
                f"New Total: {current_stock} | User: {user}")

class PPLogsModal(discord.ui.Modal):
    def __init__(self, original_view):
        super().__init__(title='Add PP Logs')
        self.original_view = original_view

    email = discord.ui.TextInput(
        label='Email',
        placeholder='Enter email...',
        required=True
    )
    password = discord.ui.TextInput(
        label='Password',
        placeholder='Enter password...',
        required=True
    )
    quantity = discord.ui.TextInput(
        label='Quantity',
        placeholder='Enter quantity to add...',
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            quantity = int(self.quantity.value)
            if quantity <= 0:
                await interaction.response.send_message("Please enter a positive number.", ephemeral=True)
                return

            # Add the specified number of PP logs with the provided details
            for _ in range(quantity):
                stock_data['pp_logs'].append({
                    'email': self.email.value,
                    'password': self.password.value
                })

            log_stock_operation("Add", "pp_logs", quantity, interaction.user.name)

            # First send the confirmation message
            await interaction.response.send_message(
                f"Added {quantity} PP logs. Current PP logs stock: {len(stock_data['pp_logs'])}",
                ephemeral=True
            )

            # Then refresh the main panel view
            if self.original_view:
                try:
                    await self.original_view.refresh_stock_view(interaction)
                except Exception as e:
                    logger.error(f"Error refreshing view after PP logs add: {str(e)}")

        except ValueError:
            await interaction.response.send_message("Please enter a valid number for quantity.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in PP Logs modal submission: {str(e)}")
            await interaction.response.send_message("An error occurred while processing your input.", ephemeral=True)

class CCModal(discord.ui.Modal):
    def __init__(self, original_view):
        super().__init__(title='Add Credit Cards')
        self.original_view = original_view

    cc_number = discord.ui.TextInput(
        label='CC Number',
        placeholder='Enter CC number...',
        required=True
    )
    cc_expiry = discord.ui.TextInput(
        label='CC MM/YY',
        placeholder='Enter expiry date...',
        required=True
    )
    cc_cvc = discord.ui.TextInput(
        label='CC CVC',
        placeholder='Enter CVC...',
        required=True
    )
    quantity = discord.ui.TextInput(
        label='Quantity',
        placeholder='Enter quantity to add...',
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            quantity = int(self.quantity.value)
            if quantity <= 0:
                await interaction.response.send_message("Please enter a positive number.", ephemeral=True)
                return

            # Add the specified number of CCs with the provided details
            for _ in range(quantity):
                stock_data['ccs'].append({
                    'number': self.cc_number.value,
                    'expiry': self.cc_expiry.value,
                    'cvc': self.cc_cvc.value
                })

            log_stock_operation("Add", "ccs", quantity, interaction.user.name)

            # First send the confirmation message
            await interaction.response.send_message(
                f"Added {quantity} CCs. Current CC stock: {len(stock_data['ccs'])}",
                ephemeral=True
            )

            # Then refresh the main panel view
            if self.original_view:
                try:
                    await self.original_view.refresh_stock_view(interaction)
                except Exception as e:
                    logger.error(f"Error refreshing view after CC add: {str(e)}")

        except ValueError:
            await interaction.response.send_message("Please enter a valid number for quantity.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in CC modal submission: {str(e)}")
            await interaction.response.send_message("An error occurred while processing your input.", ephemeral=True)

class DeleteModal(discord.ui.Modal):
    def __init__(self, stock_type: str, original_view):
        super().__init__(title='Delete Stock')
        self.stock_type = stock_type
        self.original_view = original_view

    quantity = discord.ui.TextInput(
        label='Quantity',
        placeholder='Enter quantity to delete...',
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            quantity = int(self.quantity.value)
            if quantity <= 0:
                await interaction.response.send_message("Please enter a positive number.", ephemeral=True)
                return

            current_stock = len(stock_data[self.stock_type])
            if quantity > current_stock:
                await interaction.response.send_message(
                    f"Cannot delete {quantity} items. Current stock is only {current_stock}.",
                    ephemeral=True
                )
                return

            # Remove the specified number of items from the end of the list
            for _ in range(quantity):
                stock_data[self.stock_type].pop()

            stock_type_name = "PP logs" if self.stock_type == "pp_logs" else "Credit Cards"
            log_stock_operation("Delete", self.stock_type, quantity, interaction.user.name)

            # First send the confirmation message
            await interaction.response.send_message(
                f"Deleted {quantity} {stock_type_name}. Current stock: {len(stock_data[self.stock_type])}",
                ephemeral=True
            )

            # Then refresh the main panel view
            if self.original_view:
                await self.original_view.refresh_stock_view(interaction)

        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in Delete modal submission: {str(e)}")
            await interaction.response.send_message("An error occurred while processing your input.", ephemeral=True)

class SendModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title='Send Stock')

    stock_type = discord.ui.TextInput(
        label='Type (pp_logs or ccs)',
        placeholder='Enter stock type...',
        required=True
    )
    quantity = discord.ui.TextInput(
        label='Amount',
        placeholder='Enter amount to send...',
        required=True
    )
    recipient = discord.ui.TextInput(
        label='Username/ID',
        placeholder='Enter recipient username or ID...',
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            stock_type = self.stock_type.value.lower()
            if stock_type not in ['pp_logs', 'ccs']:
                await interaction.response.send_message(
                    "Invalid stock type. Please enter 'pp_logs' or 'ccs'.",
                    ephemeral=True
                )
                return

            quantity = int(self.quantity.value)
            if quantity <= 0:
                await interaction.response.send_message("Please enter a positive number.", ephemeral=True)
                return

            current_stock = len(stock_data[stock_type])
            if quantity > current_stock:
                await interaction.response.send_message(
                    f"Cannot send {quantity} items. Current stock is only {current_stock}.",
                    ephemeral=True
                )
                return

            try:
                # Try to get user by ID first
                if self.recipient.value.isdigit():
                    recipient_user = await interaction.client.fetch_user(int(self.recipient.value))
                else:
                    # If not an ID, try to find user by name in the guild
                    guild = interaction.guild
                    recipient_user = discord.utils.get(guild.members, name=self.recipient.value)

                if recipient_user is None:
                    await interaction.response.send_message(
                        "Could not find the specified user. Please check the username/ID.",
                        ephemeral=True
                    )
                    return

                # Get the items to send
                items_to_send = stock_data[stock_type][-quantity:]
                stock_type_name = "PP logs" if stock_type == "pp_logs" else "Credit Cards"

                # Create detailed message with the actual information
                dm_message = (
                    f"🎉 You have received {quantity} {stock_type_name} from {interaction.user.name}!\n\n"
                    f"Details:\n"
                    f"- Type: {stock_type_name}\n"
                    f"- Quantity: {quantity}\n"
                    f"- Sender: {interaction.user.name}\n"
                    f"- Server: {interaction.guild.name}\n"
                    f"- Date: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
                    f"Items:\n"
                )

                # Add specific details based on the type
                for i, item in enumerate(items_to_send, 1):
                    if stock_type == 'pp_logs':
                        dm_message += f"{i}. Email: {item['email']} | Password: {item['password']}\n"
                    else:  # ccs
                        dm_message += f"{i}. CC: {item['number']} | Expiry: {item['expiry']} | CVC: {item['cvc']}\n"

                try:
                    await recipient_user.send(dm_message)
                    # Remove sent items from stock
                    stock_data[stock_type] = stock_data[stock_type][:-quantity]
                    log_stock_operation("Send", stock_type, quantity, interaction.user.name)

                    await interaction.response.send_message(
                        f"Successfully sent {quantity} {stock_type_name} to {recipient_user.name}.\n"
                        f"Current stock: {len(stock_data[stock_type])}",
                        ephemeral=True
                    )
                    await self.view.refresh_stock_view(interaction) #Refresh after send

                except discord.Forbidden:
                    await interaction.response.send_message(
                        "Could not send DM to the recipient. They might have DMs disabled.",
                        ephemeral=True
                    )
                except Exception as e:
                    logger.error(f"Error sending DM: {str(e)}")
                    await interaction.response.send_message(
                        "An error occurred while sending the DM.",
                        ephemeral=True
                    )

            except discord.NotFound:
                await interaction.response.send_message(
                    "Could not find the specified user. Please check the username/ID.",
                    ephemeral=True
                )
            except Exception as e:
                logger.error(f"Error finding user: {str(e)}")
                await interaction.response.send_message(
                    "An error occurred while finding the user.",
                    ephemeral=True
                )

        except ValueError:
            await interaction.response.send_message("Please enter a valid number for quantity.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in Send modal submission: {str(e)}")
            await interaction.response.send_message("An error occurred while processing your input.", ephemeral=True)

class SendOptionsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # No timeout for persistent view

    @discord.ui.button(
        label="Send Items",
        style=discord.ButtonStyle.primary,
        custom_id="send_items_button"
    )
    async def send_items_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(SendModal())
        except Exception as e:
            logger.error(f"Error in send items button: {str(e)}")
            await interaction.response.send_message("An error occurred while processing your request.", ephemeral=True)

    @discord.ui.button(
        label="Back to Main",
        style=discord.ButtonStyle.secondary,
        custom_id="back_button"
    )
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Stock Management",
            description="Use these buttons to manage stock:",
            color=discord.Color.purple()
        )
        embed.add_field(name="Stock", value="Check current stock", inline=False)
        embed.add_field(name="Restock", value="Add items to stock (Admin only)", inline=False)
        embed.add_field(name="Send", value="Send items from stock", inline=False)
        embed.add_field(name="Delete", value="Delete specific amount from stock (Admin only)", inline=False)
        await interaction.response.edit_message(embed=embed, view=StockButtons())



class StockButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # No timeout for persistent view

    @discord.ui.button(
        label="Stock",
        style=discord.ButtonStyle.secondary,
        custom_id="stock_button"
    )
    async def stock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Check if user has at least member role
            if not check_permissions(interaction.user, 'member'):
                await interaction.response.send_message(
                    "You need at least Member role to view stock.",
                    ephemeral=True
                )
                return

            logger.info(f"Stock button pressed by {interaction.user}")
            # Get current stock levels directly from the lists
            pp_logs_count = len(stock_data['pp_logs'])
            ccs_count = len(stock_data['ccs'])

            embed = discord.Embed(
                title="Current Stock Levels",
                description="Here are the current stock levels:",
                color=discord.Color.purple()
            )
            embed.add_field(name="PP Logs", value=str(pp_logs_count), inline=True)
            embed.add_field(name="Credit Cards", value=str(ccs_count), inline=True)

            logger.info(f"Current stock - PP Logs: {pp_logs_count}, CCs: {ccs_count}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in stock button: {str(e)}")
            await interaction.response.send_message("An error occurred while checking stock.", ephemeral=True)

    async def refresh_stock_view(self, interaction: discord.Interaction):
        """Helper method to refresh the stock view after changes"""
        try:
            embed = discord.Embed(
                title="Stock Management",
                description="Use these buttons to manage stock:",
                color=discord.Color.purple()
            )
            embed.add_field(name="Stock", value=f"PP Logs: {len(stock_data['pp_logs'])} | CCs: {len(stock_data['ccs'])}", inline=False)
            embed.add_field(name="Restock", value="Add items to stock (Admin only)", inline=False)
            embed.add_field(name="Send", value="Send items from stock", inline=False)
            embed.add_field(name="Delete", value="Delete specific amount from stock (Admin only)", inline=False)

            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.message.edit(embed=embed, view=self)
        except Exception as e:
            logger.error(f"Error in refresh_stock_view: {str(e)}")

    @discord.ui.button(
        label="Restock",
        style=discord.ButtonStyle.secondary,
        custom_id="restock_button"
    )
    async def restock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Check if user has at least manager role
            if not check_permissions(interaction.user, 'manager'):
                await interaction.response.send_message(
                    "You need Manager or Owner role to restock items.",
                    ephemeral=True
                )
                return

            logger.info(f"Restock button pressed by {interaction.user}")

            # Create a selection menu for PP logs or CCs
            select = discord.ui.Select(
                placeholder="Choose what to restock",
                options=[
                    discord.SelectOption(label="PP Logs", value="pp_logs"),
                    discord.SelectOption(label="Credit Cards", value="ccs")
                ]
            )

            async def select_callback(interaction: discord.Interaction):
                try:
                    if select.values[0] == "pp_logs":
                        await interaction.response.send_modal(PPLogsModal(original_view=self))
                    else:
                        await interaction.response.send_modal(CCModal(original_view=self))
                except Exception as e:
                    logger.error(f"Error in restock selection: {str(e)}")
                    await interaction.response.send_message("An error occurred while processing your selection.", ephemeral=True)

            select.callback = select_callback
            view = discord.ui.View()
            view.add_item(select)
            await interaction.response.send_message("Choose what to restock:", view=view, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in restock button: {str(e)}")
            await interaction.response.send_message("An error occurred while processing restock request.", ephemeral=True)

    @discord.ui.button(
        label="Send",
        style=discord.ButtonStyle.primary,
        custom_id="send_button"
    )
    async def send_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Check if user has at least member role
            logger.info(f"Send button pressed by {interaction.user} ({interaction.user.id})")
            if not check_permissions(interaction.user, 'member'):
                logger.warning(f"User {interaction.user} attempted to send without member role")
                await interaction.response.send_message(
                    "You need at least Member role to send items.",
                    ephemeral=True
                )
                return

            if len(stock_data['pp_logs']) <= 0 and len(stock_data['ccs']) <= 0:
                logger.warning("Send attempted with no stock available")
                await interaction.response.send_message(
                    "No items in stock!",
                    ephemeral=True
                )
                return

            await interaction.response.send_message("Choose send options:", view=SendOptionsView(), ephemeral=True)

        except Exception as e:
            logger.error(f"Error in send button: {str(e)}")
            await interaction.response.send_message("An error occurred while processing send request.", ephemeral=True)

    @discord.ui.button(
        label="Delete",
        style=discord.ButtonStyle.danger,
        custom_id="delete_button"
    )
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Check if user has owner role
            logger.info(f"Delete button pressed by {interaction.user} ({interaction.user.id})")
            if not check_permissions(interaction.user, 'owner'):
                logger.warning(f"User {interaction.user} attempted to delete without owner role")
                await interaction.response.send_message(
                    "You need Owner role to delete items.",
                    ephemeral=True
                )
                return

            if len(stock_data['pp_logs']) <= 0 and len(stock_data['ccs']) <= 0:
                logger.warning("Delete attempted with no stock available")
                await interaction.response.send_message(
                    "No items in stock to delete!",
                    ephemeral=True
                )
                return

            # Create a selection menu for PP logs or CCs
            select = discord.ui.Select(
                placeholder="Choose what to delete",
                options=[
                    discord.SelectOption(label="PP Logs", value="pp_logs",
                                          description=f"Current stock: {len(stock_data['pp_logs'])}"),
                    discord.SelectOption(label="Credit Cards", value="ccs",
                                          description=f"Current stock: {len(stock_data['ccs'])}")
                ]
            )

            async def select_callback(interaction: discord.Interaction):
                try:
                    logger.info(f"Delete type selected: {select.values[0]}")
                    await interaction.response.send_modal(DeleteModal(select.values[0], original_view=self))
                except Exception as e:
                    logger.error(f"Error in delete selection: {str(e)}")
                    await interaction.response.send_message(
                        "An error occurred while processing your selection.",
                        ephemeral=True
                    )

            select.callback = select_callback
            view = discord.ui.View()
            view.add_item(select)
            await interaction.response.send_message(
                "Choose what type of stock to delete:",
                view=view,
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in delete button: {str(e)}")
            await interaction.response.send_message(
                "An error occurred while processing delete request.",
                ephemeral=True
            )

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    try:
        bot.add_view(StockButtons())
        bot.add_view(SendOptionsView())
    except Exception as e:
        logger.error(f"Error adding persistent views: {str(e)}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_roles(ctx, owner_role: discord.Role, manager_role: discord.Role, member_role: discord.Role):
    """Sets up the roles for the bot"""
    global ROLES
    try:
        ROLES['owner'] = owner_role.id
        ROLES['manager'] = manager_role.id
        ROLES['member'] = member_role.id

        logger.info(f"Roles set up - Owner: {owner_role.name}, Manager: {manager_role.name}, Member: {member_role.name}")
        await ctx.send(
            f"Roles have been set up successfully!\n"
            f"Owner Role: {owner_role.mention}\n"
            f"Manager Role: {manager_role.mention}\n"
            f"Member Role: {member_role.mention}"
        )
    except Exception as e:
        logger.error(f"Error in setup_roles command: {str(e)}")
        await ctx.send("An error occurred while setting up roles. Please try again.")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_channel(ctx):
    """Sets the current channel as the stock management channel"""
    global SETUP_CHANNEL_ID
    try:
        if not all(ROLES.values()):
            await ctx.send("Please set up roles first using !setup_roles @owner_role @manager_role @member_role")
            return

        SETUP_CHANNEL_ID = ctx.channel.id
        logger.info(f"Setup channel set to {ctx.channel.name} ({ctx.channel.id})")
        await ctx.send(f"This channel has been set as the stock management channel! You can now use the !setup command here.")
    except Exception as e:
        logger.error(f"Error in setup_channel command: {str(e)}")
        await ctx.send("An error occurred while setting up the channel. Please try again.")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    """Sets up the stock management buttons"""
    global SETUP_CHANNEL_ID

    if SETUP_CHANNEL_ID is None:
        logger.warning("Setup attempted before setting channel")
        await ctx.send("Please use !setup_channel first to set the stock management channel!")
        return

    if ctx.channel.id != SETUP_CHANNEL_ID:
        logger.warning(f"Setup attempted in wrong channel by {ctx.author}")
        await ctx.send(f"This command can only be used in the designated stock management channel!")
        return

    try:
        logger.info(f"Setup command used by {ctx.author}")
        embed = discord.Embed(
            title="Stock Management",
            description="Use these buttons to manage stock:",
            color=discord.Color.purple()
        )
        embed.add_field(name="Stock", value="Check current stock", inline=False)
        embed.add_field(name="Restock", value="Add items to stock (Admin only)", inline=False)
        embed.add_field(name="Send", value="Send items from stock", inline=False)
        embed.add_field(name="Delete", value="Delete specific amount from stock (Admin only)", inline=False)

        await ctx.send(embed=embed, view=StockButtons())
    except Exception as e:
        logger.error(f"Error in setup command: {str(e)}")
        await ctx.send("An error occurred while setting up the stock management panel. Please try again.")

@setup.error
async def setup_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        logger.warning(f"User {ctx.author} attempted to use setup without permissions")
        await ctx.send("You need administrator permissions to use this command!")

@bot.event
async def on_command_error(ctx, error):
    """Global error handler for better error tracking"""
    logger.error(f"Command error occurred: {str(error)}")
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have the required permissions to use this command!")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("Command not found. Available commands: !setup_channel, !setup, !setup_roles, !price, !stock, !setuppreset")
    else:
        await ctx.send(f"An error occurred while executing the command: {str(error)}")

@bot.command()
async def price(ctx):
    """Shows price selection menu"""
    try:
        # Create a selection menu for PP logs or CCs
        select = discord.ui.Select(
            placeholder="Choose what to price check",
            options=[
                discord.SelectOption(label="PP Logs", value="pp_logs"),
                discord.SelectOption(label="Credit Cards", value="ccs")
            ]
        )

        # Calculate rates
        rates = {
            'pp_logs': 5,  # $5 per PP log
            'ccs': 10      # $10 per CC
        }

        async def select_callback(interaction: discord.Interaction):
            try:
                stock_type = select.values[0]
                stock_type_name = "PP logs" if stock_type == "pp_logs" else "Credit Cards"
                unit_price = rates[stock_type]

                # Create amounts selection
                amounts_select = discord.ui.Select(
                    placeholder=f"Choose amount of {stock_type_name}",
                    options=[
                        discord.SelectOption(label=str(amount), value=str(amount))
                        for amount in [1, 5, 10, 25, 50, 100, 250, 500]
                    ]
                )

                async def amount_callback(interaction: discord.Interaction):
                    try:
                        amount = int(amounts_select.values[0])
                        total_price = amount * unit_price

                        embed = discord.Embed(
                            title="Price Quote",
                            description="Here's your price quote:",
                            color=discord.Color.purple()
                        )
                        embed.add_field(name=f"{stock_type_name}", value=str(amount), inline=True)
                        embed.add_field(name="Price", value=f"${total_price}", inline=True)
                        embed.add_field(
                            name="How to Buy",
                            value="Make a ticket to buy",
                            inline=False
                        )

                        await interaction.response.send_message(embed=embed, ephemeral=False)  # Make visible to everyone
                    except Exception as e:
                        logger.error(f"Error in amount selection: {str(e)}")
                        await interaction.response.send_message(
                            "An error occurred while processing your selection.",
                            ephemeral=True
                        )

                amounts_select.callback = amount_callback
                amounts_view = discord.ui.View()
                amounts_view.add_item(amounts_select)
                await interaction.response.send_message(
                    f"Choose amount of {stock_type_name} to check price:",
                    view=amounts_view,
                    ephemeral=True
                )

            except Exception as e:
                logger.error(f"Error in type selection: {str(e)}")
                await interaction.response.send_message(
                    "An error occurred while processing your selection.",
                    ephemeral=True
                )

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await ctx.send("Choose what to price check:", view=view)

    except Exception as e:
        logger.error(f"Error in price command: {str(e)}")
        await ctx.send("An error occurred. Please try again.")

@price.error
async def price_error(ctx, error):
    logger.error(f"Price command error: {str(error)}")
    await ctx.send("An error occurred. Please try again.")

@bot.command()
async def stock(ctx):
    """Shows current stock levels"""
    try:
        if not check_permissions(ctx.author, 'member'):
            await ctx.send(
                "You need at least Member role to view stock.",
                ephemeral=True
            )
            return

        # Get current stock levels
        pp_logs_count = len(stock_data['pp_logs'])
        ccs_count = len(stock_data['ccs'])

        embed = discord.Embed(
            title="Current Stock Levels",
            description="Here are the current stock levels:",
            color=discord.Color.purple()
        )
        embed.add_field(name="PP Logs", value=str(pp_logs_count), inline=True)
        embed.add_field(name="Credit Cards", value=str(ccs_count), inline=True)

        await ctx.send(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"Error in stock command: {str(e)}")
        await ctx.send("An error occurred while checking stock.", ephemeral=True)

@stock.error
async def stock_error(ctx, error):
    """Error handler for stock command"""
    logger.error(f"Stock command error: {str(error)}")
    await ctx.send("An error occurred while checking stock.", ephemeral=True)

@bot.command()
@commands.has_permissions(administrator=True)
async def setuppreset(ctx):
    """Creates a preset channel for stock management"""
    try:
        await setup_channel(ctx)
        await setup(ctx)
    except Exception as e:
        logger.error(f"Error in setuppreset command: {str(e)}")
        await ctx.send("An error occurred while setting up the preset. Please try again.")

# Run the bot
if __name__ == "__main__":
    try:
        from keep_alive import keep_alive
        keep_alive()  # Start the keep-alive flask server in a separate thread
        logger.info("Keep-alive server started")
        bot.run(TOKEN)  # This will run in the main thread
    except Exception as e:
        logger.error(f"Error starting the bot: {e}")