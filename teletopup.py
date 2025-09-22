import os
import logging
import json
import uuid
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import asyncio
import sqlite3

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = "8323472179:AAH6IqJ3MWeQ8_4m8-yICakU0WPn48U5Xgw"  # Replace with your bot token
ADMIN_IDS = [7461947639, 1555255959]  # Replace with admin Telegram user IDs
PAYMENT_QR_IMAGE = "qr.jpg"  # Path to your QR code image

# Database setup
def init_db():
    conn = sqlite3.connect('robux_bot.db')
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            roblox_username TEXT
        )
    ''')
    
    # Create transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            roblox_username TEXT,
            robux_amount INTEGER,
            price REAL,
            status TEXT DEFAULT 'pending',
            payment_proof TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Robux packages configuration
ROBUX_PACKAGES = {
    "80": {"robux": 80, "price": 1.0},
    "160": {"robux": 160, "price": 2.0},
    "240": {"robux": 240, "price": 3.0},
    "400": {"robux": 400, "price": 5.0},
    "800": {"robux": 800, "price": 10.0},
    "1700": {"robux": 1700, "price": 20.0},
    "4500": {"robux": 4500, "price": 50.0},
    "10000": {"robux": 10000, "price": 100.0}
}

class RobuxBot:
    def __init__(self):
        init_db()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        user = update.effective_user
        self.save_user(user.id, user.username)
        
        welcome_text = f"""
🎮 **Welcome to Robux Top-up Bot!** 🎮

Hello {user.first_name}! 

This bot helps you purchase Robux for your Roblox account safely and easily.

**How it works:**
1️⃣ Choose your Robux package
2️⃣ Enter your Roblox username
3️⃣ Make payment via QR code
4️⃣ Upload payment proof
5️⃣ Wait for admin approval
6️⃣ Receive your Robux!

Use /buy to start purchasing Robux
Use /status to check your transaction status
Use /help for more information
        """
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command handler"""
        help_text = """
🆘 **Help - How to use this bot**

**Available Commands:**
/start - Start the bot
/buy - Purchase Robux packages
/status - Check transaction status
/help - Show this help message

**How to buy Robux:**
1. Use /buy command
2. Select package from menu
3. Enter your Roblox username
4. Pay using the QR code
5. Upload screenshot of payment
6. Wait for admin approval

**Payment Methods:**
💳 Bank Transfer
💰 E-wallet
📱 Mobile Banking

**Support:**
If you have any issues, contact our admin team.
        """
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def buy_robux(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Buy robux command handler"""
        keyboard = []
        
        for package_id, package_info in ROBUX_PACKAGES.items():
            robux = package_info["robux"]
            price = package_info["price"]
            button_text = f"💎 {robux} Robux - ${price}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"package_{package_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = """
🛒 **Choose your Robux package:**

Select the amount of Robux you want to purchase:
        """
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def package_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle package selection"""
        query = update.callback_query
        await query.answer()
        
        package_id = query.data.replace("package_", "")
        package_info = ROBUX_PACKAGES[package_id]
        
        # Store selected package in user context
        context.user_data['selected_package'] = package_id
        context.user_data['robux_amount'] = package_info['robux']
        context.user_data['price'] = package_info['price']
        
        text = f"""
✅ **Package Selected:**
💎 Robux: {package_info['robux']}
💰 Price: ${package_info['price']}

Please enter your **Roblox Username** to continue:
        """
        
        await query.edit_message_text(text, parse_mode='Markdown')
        context.user_data['waiting_for'] = 'roblox_username'
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        if 'waiting_for' not in context.user_data:
            await update.message.reply_text("Please use /buy to start a purchase or /help for assistance.")
            return
        
        if context.user_data['waiting_for'] == 'roblox_username':
            roblox_username = update.message.text.strip()
            context.user_data['roblox_username'] = roblox_username
            
            # Create transaction
            transaction_id = str(uuid.uuid4())[:8].upper()
            user_id = update.effective_user.id
            
            conn = sqlite3.connect('robux_bot.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO transactions (id, user_id, roblox_username, robux_amount, price)
                VALUES (?, ?, ?, ?, ?)
            ''', (transaction_id, user_id, roblox_username, 
                 context.user_data['robux_amount'], context.user_data['price']))
            conn.commit()
            conn.close()
            
            context.user_data['transaction_id'] = transaction_id
            
            # Send payment instructions
            await self.send_payment_instructions(update, context)
    
    async def send_payment_instructions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send payment instructions with QR code"""
        transaction_id = context.user_data['transaction_id']
        robux_amount = context.user_data['robux_amount']
        price = context.user_data['price']
        roblox_username = context.user_data['roblox_username']
        
        payment_text = f"""
💳 **Payment Instructions**

**Transaction ID:** `{transaction_id}`
**Roblox Username:** {roblox_username}
**Robux Amount:** {robux_amount}
**Total Price:** ${price}

**Payment Methods:**
📱 Scan the QR code below to make payment
💰 Bank Transfer / E-wallet / Mobile Banking

⚠️ **Important:**
1. Pay the exact amount: ${price}
2. Take a screenshot of successful payment
3. Send the screenshot to this chat
4. Wait for admin approval

**Next Step:** Send your payment proof screenshot 📸
        """
        
        try:
            # Send QR code image
            with open(PAYMENT_QR_IMAGE, 'rb') as photo:
                await update.message.reply_photo(
                    photo=photo,
                    caption=payment_text,
                    parse_mode='Markdown'
                )
        except FileNotFoundError:
            # If QR image not found, send text only
            await update.message.reply_text(payment_text, parse_mode='Markdown')
            await update.message.reply_text("⚠️ QR code image not available. Please contact admin for payment details.")
        
        context.user_data['waiting_for'] = 'payment_proof'
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo uploads (payment proof)"""
        if 'waiting_for' not in context.user_data or context.user_data['waiting_for'] != 'payment_proof':
            await update.message.reply_text("Please start a purchase with /buy first.")
            return
        
        # Get the highest resolution photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        # Save photo
        transaction_id = context.user_data['transaction_id']
        photo_path = f"payment_proofs/{transaction_id}.jpg"
        os.makedirs("payment_proofs", exist_ok=True)
        await file.download_to_drive(photo_path)
        
        # Update database
        conn = sqlite3.connect('robux_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE transactions SET payment_proof = ? WHERE id = ?
        ''', (photo_path, transaction_id))
        conn.commit()
        conn.close()
        
        # Notify user
        await update.message.reply_text("""
✅ **Payment proof received!**

Your payment proof has been submitted successfully.
Our admin team will review it shortly.

**What happens next:**
⏳ Admin will verify your payment
✅ You'll receive approval notification
🎮 Robux will be added to your account

Use /status to check your transaction status.
        """, parse_mode='Markdown')
        
        # Notify admins
        await self.notify_admins(context, transaction_id)
        
        # Clear user context
        context.user_data.clear()
    
    async def notify_admins(self, context: ContextTypes.DEFAULT_TYPE, transaction_id):
        """Notify admins about new payment proof"""
        conn = sqlite3.connect('robux_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT t.*, u.username FROM transactions t
            JOIN users u ON t.user_id = u.user_id
            WHERE t.id = ?
        ''', (transaction_id,))
        transaction = cursor.fetchone()
        conn.close()
        
        if not transaction:
            logger.error(f"Transaction {transaction_id} not found in database")
            return
        
        # Handle case where username might be None
        username = transaction[7] if transaction[7] else "Unknown"
        
        admin_text = f"""
🔔 **New Payment Proof Submitted**

**Transaction ID:** `{transaction[0]}`
**User:** @{username} (ID: {transaction[1]})
**Roblox Username:** {transaction[2]}
**Robux Amount:** {transaction[3]}
**Price:** ${transaction[4]}
**Status:** {transaction[5]}
**Submitted:** {transaction[6]}

Please review the payment proof and take action.
        """
        
        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{transaction_id}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_{transaction_id}")],
            [InlineKeyboardButton("📸 View Proof", callback_data=f"viewproof_{transaction_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Check if ADMIN_IDS is properly configured
        if not ADMIN_IDS:
            logger.error("No admin IDs configured! Please add admin IDs to ADMIN_IDS list.")
            return
        
        logger.info(f"Attempting to notify {len(ADMIN_IDS)} admins about transaction {transaction_id}")
        
        success_count = 0
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                logger.info(f"Successfully notified admin {admin_id}")
                success_count += 1
                
                # Also send the payment proof image to admin
                try:
                    photo_path = transaction[6]  # payment_proof path
                    if photo_path and os.path.exists(photo_path):
                        with open(photo_path, 'rb') as photo:
                            await context.bot.send_photo(
                                chat_id=admin_id,
                                photo=photo,
                                caption=f"Payment proof for transaction: {transaction_id}"
                            )
                        logger.info(f"Payment proof sent to admin {admin_id}")
                except Exception as photo_error:
                    logger.error(f"Failed to send payment proof to admin {admin_id}: {photo_error}")
                    
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
                # Try to send a simple text message if markdown fails
                try:
                    simple_text = f"🔔 New payment proof submitted for transaction {transaction_id}\nUser ID: {transaction[1]}\nRoblox: {transaction[2]}\nRobux: {transaction[3]}\nPrice: ${transaction[4]}"
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=simple_text,
                        reply_markup=reply_markup
                    )
                    logger.info(f"Sent simple notification to admin {admin_id}")
                    success_count += 1
                except Exception as simple_error:
                    logger.error(f"Failed to send simple notification to admin {admin_id}: {simple_error}")
        
        if success_count == 0:
            logger.critical("Failed to notify any admin! Check admin IDs and bot permissions.")
        else:
            logger.info(f"Successfully notified {success_count}/{len(ADMIN_IDS)} admins")
    
    async def admin_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin approve/reject actions"""
        query = update.callback_query
        await query.answer()
        
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Unauthorized access!", show_alert=True)
            return
        
        action, transaction_id = query.data.split("_", 1)
        
        if action == "approve":
            await self.approve_transaction(query, transaction_id, context)
        elif action == "reject":
            await self.reject_transaction(query, transaction_id, context)
        elif action == "viewproof":
            await self.view_payment_proof(query, transaction_id, context)
    
    async def approve_transaction(self, query, transaction_id, context):
        """Approve a transaction"""
        conn = sqlite3.connect('robux_bot.db')
        cursor = conn.cursor()
        
        # Update transaction status
        cursor.execute('''
            UPDATE transactions SET status = 'approved', approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (transaction_id,))
        
        # Get transaction details
        cursor.execute('''
            SELECT t.*, u.username FROM transactions t
            JOIN users u ON t.user_id = u.user_id
            WHERE t.id = ?
        ''', (transaction_id,))
        transaction = cursor.fetchone()
        conn.commit()
        conn.close()
        
        if not transaction:
            await query.edit_message_text("❌ Transaction not found!")
            return
        
        # Notify user
        user_text = f"""
✅ **Payment Approved!**

**Transaction ID:** `{transaction_id}`
**Robux Amount:** {transaction[3]}
**Roblox Username:** {transaction[2]}

🎉 Your payment has been approved!
💎 {transaction[3]} Robux will be added to your Roblox account within 24 hours.

Thank you for using our service!
        """
        
        try:
            await context.bot.send_message(
                chat_id=transaction[1],
                text=user_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")
        
        # Update admin message
        await query.edit_message_text(
            f"✅ **Transaction {transaction_id} APPROVED**\n\n"
            f"User @{transaction[7]} has been notified.",
            parse_mode='Markdown'
        )
    
    async def reject_transaction(self, query, transaction_id, context):
        """Reject a transaction"""
        conn = sqlite3.connect('robux_bot.db')
        cursor = conn.cursor()
        
        # Update transaction status
        cursor.execute('''
            UPDATE transactions SET status = 'rejected'
            WHERE id = ?
        ''', (transaction_id,))
        
        # Get transaction details
        cursor.execute('''
            SELECT t.*, u.username FROM transactions t
            JOIN users u ON t.user_id = u.user_id
            WHERE t.id = ?
        ''', (transaction_id,))
        transaction = cursor.fetchone()
        conn.commit()
        conn.close()
        
        if not transaction:
            await query.edit_message_text("❌ Transaction not found!")
            return
        
        # Notify user
        user_text = f"""
❌ **Payment Rejected**

**Transaction ID:** `{transaction_id}`

Unfortunately, your payment proof was rejected.
This could be due to:
• Invalid payment amount
• Poor quality screenshot
• Payment not received

Please contact admin for more information or try again with correct payment proof.
        """
        
        try:
            await context.bot.send_message(
                chat_id=transaction[1],
                text=user_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")
        
        # Update admin message
        await query.edit_message_text(
            f"❌ **Transaction {transaction_id} REJECTED**\n\n"
            f"User @{transaction[7]} has been notified.",
            parse_mode='Markdown'
        )
    
    async def view_payment_proof(self, query, transaction_id, context):
        """View payment proof"""
        conn = sqlite3.connect('robux_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT payment_proof FROM transactions WHERE id = ?', (transaction_id,))
        result = cursor.fetchone()
        conn.close()
        
        if not result or not result[0]:
            await query.answer("❌ No payment proof found!", show_alert=True)
            return
        
        try:
            with open(result[0], 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=query.from_user.id,
                    photo=photo,
                    caption=f"Payment proof for transaction: {transaction_id}"
                )
        except FileNotFoundError:
            await query.answer("❌ Payment proof file not found!", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ Error viewing proof: {str(e)}", show_alert=True)
    
    async def check_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check transaction status"""
        user_id = update.effective_user.id
        
        conn = sqlite3.connect('robux_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM transactions WHERE user_id = ? 
            ORDER BY created_at DESC LIMIT 5
        ''', (user_id,))
        transactions = cursor.fetchall()
        conn.close()
        
        if not transactions:
            await update.message.reply_text("You have no transactions yet. Use /buy to make your first purchase!")
            return
        
        status_text = "📊 **Your Recent Transactions:**\n\n"
        
        for trans in transactions:
            status_emoji = {
                'pending': '⏳',
                'approved': '✅',
                'rejected': '❌'
            }.get(trans[5], '❓')
            
            status_text += f"""
{status_emoji} **{trans[0]}**
• Robux: {trans[3]}
• Price: ${trans[4]}
• Status: {trans[5].upper()}
• Date: {trans[6][:16]}
            """
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
    
    def save_user(self, user_id, username):
        """Save user to database"""
        conn = sqlite3.connect('robux_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username)
            VALUES (?, ?)
        ''', (user_id, username))
        conn.commit()
        conn.close()

def main():
    """Main function to run the bot"""
    # Create bot instance
    bot = RobuxBot()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("buy", bot.buy_robux))
    application.add_handler(CommandHandler("status", bot.check_status))
    
    # Callback query handler
    application.add_handler(CallbackQueryHandler(bot.package_selected, pattern="^package_"))
    application.add_handler(CallbackQueryHandler(bot.admin_action, pattern="^(approve|reject|viewproof)_"))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_text_message))
    application.add_handler(MessageHandler(filters.PHOTO, bot.handle_photo))
    
    # Start the bot
    print("🤖 Robux Top-up Bot is starting...")
    print(f"🔑 Bot Token: {BOT_TOKEN[:10]}...")
    print(f"👥 Admin IDs: {ADMIN_IDS}")
    print("🚀 Bot is running! Press Ctrl+C to stop.")
    
    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()