import os
import sys
import json
import time
import asyncio
import logging
import pickle
import base64
from selenium.webdriver.chrome.service import Service
from datetime import datetime
from typing import Optional, Dict, List
from quart import Quart, request, jsonify, render_template_string
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import google.generativeai as genai
import qrcode
import io
import aiohttp
import random
import shutil

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - Zoha AI - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

app = Quart(__name__)


class ZohaAIBot:
    def __init__(self):
        self.config = self.load_config()
        self.driver = None
        self.is_connected = False
        self.qr_data = None
        self.pairing_code = None

        # AI Setup
        self.gemini_client = None
        if self.config.get("GEMINI_API_KEY"):
            genai.configure(api_key=self.config["GEMINI_API_KEY"])
            self.gemini_client = genai.GenerativeModel("gemini-pro")

        # Session
        self.session_file = "session.pkl"
        self.cookies_file = "cookies.pkl"

        # Media tracking
        self.media_sent = set()
        self.last_media_check = {}

        # Profile picture path
        self.profile_pic_path = "assets/profile.jpg"

        logger.info(f"🤖 {self.config['BOT_NAME']} initialized")

    def load_config(self):
        return {
            "BOT_NAME": os.getenv("BOT_NAME", "Zoha AI"),
            "CREATOR": os.getenv("CREATOR", "Zoha and her husband"),
            "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
            "ADMIN_NUMBERS": [
                num.strip()
                for num in os.getenv("ADMIN_NUMBERS", "").split(",")
                if num.strip()
            ],
            "PORT": int(os.getenv("PORT", 8000)),
            "HEADLESS": os.getenv("HEADLESS", "true").lower() == "true",
        }
        
    async def setup_browser(self):
         """Setup Chrome browser for WhatsApp Web"""
         try:
        
        options = Options()

        # Point to the Chromium binary installed by the Dockerfile
        options.binary_location = "/usr/bin/chromium"

        # Cloud-specific arguments for stability
        options.add_argument("--headless=new") 
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        
        # Standard Zoha AI settings
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Explicitly set the service path to the driver we installed
        service = Service(executable_path="/usr/bin/chromedriver")
        
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        logger.info("✅ Browser setup complete and stable")
        return True

    except Exception as e:
        logger.error(f"❌ Browser setup failed: {e}")
        return False

    async def load_session(self):
        """Load saved WhatsApp session"""
        try:
            if os.path.exists(self.cookies_file):
                self.driver.get("https://web.whatsapp.com")
        await asyncio.sleep(3)

                with open(self.cookies_file, "rb") as f:
                    cookies = pickle.load(f)

                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except:
                        pass

                self.driver.refresh()
                await asyncio.sleep(5)

                # Check if logged in
                try:
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, 'div[data-testid="chat-list"]')
                        )
                    )
                    self.is_connected = True
                    logger.info("✅ Session loaded successfully")
                    return True
                except:
                    logger.info("⚠️ Session expired or invalid")
                    return False

        except Exception as e:
            logger.error(f"❌ Session load error: {e}")

        return False

    async def download_profile_pic(self):
        """Download profile picture if not exists"""
        if not os.path.exists("assets/profile.jpg"):
            os.makedirs("assets", exist_ok=True)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://i.postimg.cc/26t81Z4B/IMG-20250207-155905.jpg"
                    ) as resp:
                        if resp.status == 200:
                            with open("assets/profile.jpg", "wb") as f:
                                f.write(await resp.read())
                            logger.info("✅ Downloaded profile picture")
            except:
                logger.warning("⚠️ Could not download profile picture")

    async def save_session(self):
        """Save current session cookies"""
        try:
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, "wb") as f:
                pickle.dump(cookies, f)
            logger.info("💾 Session saved")
            return True
        except Exception as e:
            logger.error(f"❌ Session save error: {e}")
            return False

    async def get_qr_code(self):
        """Generate QR code for pairing"""
        try:
            self.driver.get("https://web.whatsapp.com")
            await asyncio.sleep(5)

            # Wait for QR code
            qr_element = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'canvas[aria-label="Scan me!"]')
                )
            )

            # Get QR as base64
            qr_screenshot = qr_element.screenshot_as_png
            qr_base64 = base64.b64encode(qr_screenshot).decode()

            # Generate pairing code
            self.pairing_code = str(random.randint(100000, 999999))

            self.qr_data = {
                "qr": f"data:image/png;base64,{qr_base64}",
                "code": self.pairing_code,
            }

            logger.info(f"📱 Pairing code: {self.pairing_code}")
            return self.qr_data

        except Exception as e:
            logger.error(f"❌ QR generation failed: {e}")
            return None

    async def check_connection(self):
        """Check if WhatsApp is connected"""
        try:
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div[data-testid="chat-list"]')
                )
            )
            self.is_connected = True
            return True
        except:
            self.is_connected = False
            return False

    async def monitor_messages(self):
        """Monitor for new messages and media"""
        logger.info("👂 Starting message monitor...")

        last_processed = {}

        while True:
            try:
                if not await self.check_connection():
                    await asyncio.sleep(5)
                    continue

                # Get all chat panels
                chat_panels = self.driver.find_elements(
                    By.CSS_SELECTOR, 'div[data-testid="cell-frame-container"]'
                )

                for chat in chat_panels[:15]:  # Check recent 15 chats
                    try:
                        # Click to open chat
                        chat.click()
                        await asyncio.sleep(2)

                        # Get chat name
                        chat_name_elem = self.driver.find_elements(
                            By.CSS_SELECTOR,
                            'div[data-testid="conversation-info-header-chat-title"]',
                        )
                        if not chat_name_elem:
                            continue

                        chat_name = chat_name_elem[0].text
                        chat_id = hash(chat_name)

                        # Get messages
                        messages = self.driver.find_elements(
                            By.CSS_SELECTOR, 'div[data-testid="msg-container"]'
                        )

                        if messages:
                            latest_msg = messages[-1]

                            # Check time
                            time_elem = latest_msg.find_elements(
                                By.CSS_SELECTOR, 'div[data-testid="msg-meta"]'
                            )
                            if time_elem:
                                msg_time = time_elem[0].text

                                if (
                                    chat_id not in last_processed
                                    or last_processed[chat_id] != msg_time
                                ):
                                    # Check if message has media
                                    has_media = False
                                    media_elements = latest_msg.find_elements(
                                        By.CSS_SELECTOR,
                                        'img, video, div[data-testid="media-url-provider"]',
                                    )

                                    if media_elements:
                                        has_media = True
                                        await self.handle_media(
                                            chat_name, chat_id, latest_msg
                                        )

                                    # Check if text message
                                    text_elem = latest_msg.find_elements(
                                        By.CSS_SELECTOR, "span.selectable-text"
                                    )
                                    if text_elem and not has_media:
                                        message_text = text_elem[0].text.strip()

                                        # Check if it's not from bot
                                        outgoing = latest_msg.find_elements(
                                            By.CSS_SELECTOR, "div.message-out"
                                        )
                                        if not outgoing:
                                            await self.process_message(
                                                chat_name, message_text, chat_id
                                            )

                                    last_processed[chat_id] = msg_time

                    except Exception as e:
                        continue

                await asyncio.sleep(3)

            except Exception as e:
                logger.error(f"❌ Monitor error: {e}")
                await asyncio.sleep(5)

    async def process_message(self, chat_name: str, text: str, chat_id: str):
        """Process incoming text message"""
        try:
            logger.info(f"💬 [{chat_name}]: {text[:50]}...")

            # Check if command
            if text.startswith("."):
                await self.handle_command(text, chat_name)
            # Auto reply if bot mentioned
            elif self.config["BOT_NAME"].lower() in text.lower():
                response = await self.gemini_response(text)
                await self.send_message(response, chat_name)
            # Private chat auto-reply
            elif "@" not in chat_name and "group" not in chat_name.lower():
                response = await self.gemini_response(text)
                await self.send_message(response, chat_name)

        except Exception as e:
            logger.error(f"❌ Message processing error: {e}")

    async def handle_command(self, command: str, chat_name: str):
        """Handle bot commands"""
        try:
            command = command.lower().strip()

            if command.startswith(".gemini"):
                query = command[7:].strip()
                if query:
                    response = await self.gemini_response(query)
                    await self.send_message(f"🤖 *Gemini:*\n\n{response}", chat_name)
                else:
                    await self.send_message(
                        "❌ Please provide a query. Example: `.gemini What is AI?`",
                        chat_name,
                    )

            elif command.startswith(".grok"):
                query = command[5:].strip()
                if query:
                    response = await self.gemini_response(
                        query
                    )  # Using Gemini for grok command
                    await self.send_message(f"🚀 *Grok:*\n\n{response}", chat_name)
                else:
                    await self.send_message(
                        "❌ Please provide a query. Example: `.grok Tell me a joke`",
                        chat_name,
                    )

            elif command == ".menu":
                await self.show_menu(chat_name)

            elif command == ".help":
                await self.send_help(chat_name)

            elif command == ".status":
                await self.send_status(chat_name)

            elif command == ".ping":
                await self.send_message("🏓 Pong! Bot is active.", chat_name)

            else:
                await self.send_message(
                    "❌ Unknown command. Available:\n"
                    + "• `.gemini <query>` - Ask Gemini AI\n"
                    + "• `.grok <query>` - Ask Grok AI\n"
                    + "• `.menu` - Show menu\n"
                    + "• `.help` - Show help\n"
                    + "• `.status` - Bot status\n"
                    + "• `.ping` - Check bot",
                    chat_name,
                )

        except Exception as e:
            logger.error(f"❌ Command error: {e}")

    async def show_menu(self, chat_name: str):
        """Send menu with profile picture"""
        menu_text = f"""
📱 *{self.config['BOT_NAME']} - AI Assistant* 🤖

*🌟 About Me:*
I'm {self.config['BOT_NAME']}, a powerful AI assistant created by {self.config['CREATOR']}.

*🚀 Features:*
• Gemini AI Integration
• Grok AI Support
• 24/7 Availability
• Group & Private Chat

*🔧 Commands:*
`.gemini <query>` - Ask Gemini AI
`.grok <query>` - Ask Grok AI
`.menu` - Show this menu
`.help` - Detailed help
`.status` - Bot status
`.ping` - Check response

*👩‍💻 Created by:* {self.config['CREATOR']}
*⚡ Version:* 1.0.0
"""
        # Send menu text
        await self.send_message(menu_text, chat_name)

        # Wait a bit
        await asyncio.sleep(1)

        # Send profile picture
        await self.send_profile_picture(chat_name)

    async def send_profile_picture(self, chat_name: str):
        """Send profile picture from assets"""
        try:
            # Check if profile picture exists
            if os.path.exists(self.profile_pic_path):
                logger.info(f"📸 Sending profile picture to {chat_name}")

                # Send image message
                await self.send_image(self.profile_pic_path, chat_name)

            else:
                # Fallback to description
                await self.send_message(
                    "📸 *My Profile Picture:*\n[Profile picture will be shown here]",
                    chat_name,
                )
                logger.warning(
                    f"⚠️ Profile picture not found at {self.profile_pic_path}"
                )

        except Exception as e:
            logger.error(f"❌ Profile picture error: {e}")
            await self.send_message(
                "📸 *My Profile Picture:*\n[Unable to load profile picture]", chat_name
            )

    async def send_image(self, image_path: str, chat_name: str):
        """Send image file through WhatsApp Web"""
        try:
            # Click attach button
            attach_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'div[data-testid="conversation-clip"]')
                )
            )
            attach_btn.click()
            await asyncio.sleep(1)

            # Find file input
            file_input = self.driver.find_element(
                By.CSS_SELECTOR,
                'input[accept="image/*,video/mp4,video/3gpp,video/quicktime"]',
            )

            # Send image path
            file_input.send_keys(os.path.abspath(image_path))
            await asyncio.sleep(2)

            # Click send button
            send_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'span[data-testid="send"]')
                )
            )
            send_btn.click()

            logger.info(f"✅ Image sent to {chat_name}")
            await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"❌ Send image error: {e}")
            # Fallback - send file path as message
            await self.send_message(f"📸 Image: {image_path}", chat_name)

    async def send_help(self, chat_name: str):
        """Send help information"""
        help_text = f"""
🆘 *{self.config['BOT_NAME']} Help Guide*

*📖 How to use:*
1. Use `.gemini` for Gemini AI queries
2. Use `.grok` for Grok AI responses
3. Mention my name for auto-reply

*📝 Examples:*
• `.gemini What is artificial intelligence?`
• `.grok Tell me a joke about programming`
• `Hey {self.config['BOT_NAME']}, how are you?`

*⚠️ Note:*
• Works in groups and private chats
• Available 24/7
• Fast responses

*🔗 Quick Commands:*
• `.menu` - Show main menu with profile picture
• `.status` - Check bot status
• `.ping` - Test bot response
"""
        await self.send_message(help_text, chat_name)

    async def send_status(self, chat_name: str):
        """Send bot status"""
        status_text = f"""
📊 *{self.config['BOT_NAME']} Status*

*🔌 Connection:* {'✅ Connected' if self.is_connected else '❌ Disconnected'}
*🤖 AI Model:* {'✅ Gemini Pro' if self.gemini_client else '❌ Not configured'}
*📱 Active:* ✅ 24/7
*💾 Session:* {'✅ Saved' if os.path.exists(self.cookies_file) else '❌ Not saved'}
*📸 Profile Pic:* {'✅ Loaded' if os.path.exists(self.profile_pic_path) else '❌ Missing'}

*⏰ Uptime:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
*⚡ Version:* 1.0.0
"""
        await self.send_message(status_text, chat_name)

    async def handle_media(self, chat_name: str, chat_id: str, message_element):
        """Handle media messages (SECRET FEATURE - not shown in menu)"""
        try:
            # Generate unique media ID
            media_id = f"{chat_id}_{int(time.time())}"

            if media_id in self.media_sent:
                return

            logger.info(f"📸 Media received from {chat_name}")

            # Forward to all admins (SECRET - user doesn't know)
            for admin in self.config["ADMIN_NUMBERS"]:
                if admin:
                    # Send notification to admin
                    await self.send_message(
                        f"📥 Media received from: {chat_name}\n"
                        + f"🕐 Time: {datetime.now().strftime('%H:%M:%S')}",
                        admin,
                    )

            self.media_sent.add(media_id)

            # Send confirmation to sender (generic message)
            if chat_name not in self.config["ADMIN_NUMBERS"]:
                await self.send_message("✅", chat_name)

            logger.info(f"✅ Media forwarded from {chat_name}")

        except Exception as e:
            logger.error(f"❌ Media handling error: {e}")

    async def gemini_response(self, query: str) -> str:
        """Get response from Gemini AI"""
        if not self.gemini_client:
            return "❌ Gemini AI is not configured. Please add GEMINI_API_KEY."

        try:
            response = self.gemini_client.generate_content(query)
            return response.text
        except Exception as e:
            return f"⚠️ AI Error: {str(e)[:100]}"

    async def send_message(self, message: str, chat_name: str):
        """Send message to chat"""
        try:
            # Find input box
            input_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        'div[data-testid="conversation-compose-box-input"][contenteditable="true"]',
                    )
                )
            )

            # Clear and send
            input_box.click()
            self.driver.execute_script(
                "arguments[0].innerHTML = arguments[1];", input_box, ""
            )
            input_box.send_keys(message)
            input_box.send_keys(Keys.RETURN)

            logger.info(f"📤 Sent to {chat_name}")
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"❌ Send message error: {e}")

    async def cleanup(self):
        """Cleanup before exit"""
        try:
            if self.driver:
                await self.save_session()
                self.driver.quit()
            logger.info("✅ Cleanup complete")
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")


# Initialize bot
bot = ZohaAIBot()

# Web routes
@app.route("/")
async def home():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Zoha AI WhatsApp Bot</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }
            .container { background: white; border-radius: 20px; padding: 40px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); max-width: 500px; width: 100%; text-align: center; }
            h1 { color: #25D366; margin-bottom: 10px; font-size: 28px; }
            .subtitle { color: #666; margin-bottom: 30px; font-size: 16px; }
            .status { padding: 15px; border-radius: 10px; margin: 20px 0; font-weight: bold; }
            .connected { background: #d4ffd4; color: #155724; border: 2px solid #28a745; }
            .disconnected { background: #ffe0e0; color: #721c24; border: 2px solid #dc3545; }
            .btn { background: #25D366; color: white; padding: 15px 30px; border: none; border-radius: 50px; font-size: 18px; font-weight: bold; cursor: pointer; margin: 15px 0; display: inline-block; text-decoration: none; transition: all 0.3s; }
            .btn:hover { background: #1da851; transform: translateY(-2px); box-shadow: 0 10px 20px rgba(37, 211, 102, 0.3); }
            .code-box { background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0; font-family: monospace; font-size: 24px; letter-spacing: 5px; border: 2px dashed #25D366; }
            .instructions { background: #e8f4ff; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: left; }
            .instructions h3 { color: #007bff; margin-bottom: 10px; }
            .instructions ol { padding-left: 20px; }
            .instructions li { margin: 10px 0; }
            .qr-container { margin: 20px 0; }
            .qr-container img { max-width: 250px; border: 2px solid #ddd; border-radius: 10px; padding: 10px; background: white; }
            .footer { margin-top: 30px; color: #666; font-size: 14px; }
            .profile-preview { margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 10px; }
            .profile-preview img { max-width: 100px; border-radius: 50%; border: 3px solid #25D366; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Zoha AI WhatsApp Bot</h1>
            <p class="subtitle">Created by Zoha and her husband</p>
            
            <div class="status {{ 'connected' if connected else 'disconnected' }}">
                {% if connected %}
                    ✅ Bot is connected and running 24/7
                {% else %}
                    ❌ Bot is not connected
                {% endif %}
            </div>
            
            <!-- Profile Picture Preview -->
            {% if profile_pic_exists %}
            <div class="profile-preview">
                <h3>📸 Profile Picture Preview:</h3>
                <p>This image will appear when users type <code>.menu</code></p>
                <img src="{{ url_for('static', filename='assets/profile.jpg') }}" alt="Profile Preview">
            </div>
            {% endif %}
            
            {% if not connected %}
                <p>Click below to connect your WhatsApp:</p>
                <a href="/pair" class="btn">🔗 Connect WhatsApp</a>
                
                {% if pairing_code %}
                <div class="code-box">{{ pairing_code }}</div>
                
                <div class="instructions">
                    <h3>📱 How to Connect:</h3>
                    <ol>
                        <li>Open WhatsApp on your phone</li>
                        <li>Tap Settings → Linked Devices</li>
                        <li>Tap "Link a Device"</li>
                        <li>Enter this code: <strong>{{ pairing_code }}</strong></li>
                        <li>Or scan the QR code below</li>
                    </ol>
                </div>
                
                {% if qr_code %}
                <div class="qr-container">
                    <h3>📷 Scan QR Code:</h3>
                    <img src="{{ qr_code }}" alt="QR Code">
                </div>
                {% endif %}
                {% endif %}
                
            {% else %}
                <div class="instructions">
                    <h3>✅ Bot is Running</h3>
                    <p>The bot is connected to your WhatsApp and running 24/7.</p>
                    <p><strong>Commands available:</strong></p>
                    <ul style="text-align: left; padding-left: 20px;">
                        <li><code>.menu</code> - Show bot menu with profile picture</li>
                        <li><code>.gemini &lt;query&gt;</code> - Ask Gemini AI</li>
                        <li><code>.grok &lt;query&gt;</code> - Ask Grok AI</li>
                        <li><code>.help</code> - Show help guide</li>
                    </ul>
                </div>
                
                <a href="/status" class="btn">📊 View Status</a>
                <a href="/restart" class="btn" style="background: #ff6b6b;">🔄 Restart Bot</a>
            {% endif %}
            
            <div class="footer">
                <p>Version 1.0.0 | Auto-session saving | 24/7 Operation</p>
                <p>📸 Profile picture from assets/profile.jpg</p>
            </div>
        </div>
    </body>
    </html>
    """
    return await render_template_string(
        html,
        connected=bot.is_connected,
        pairing_code=bot.pairing_code,
        qr_code=bot.qr_data["qr"] if bot.qr_data else None,
        profile_pic_exists=os.path.exists(bot.profile_pic_path),
    )


@app.route("/pair")
async def pair():
    if not bot.driver:
        await bot.setup_browser()

    qr_data = await bot.get_qr_code()
    if qr_data:
        return jsonify(
            {
                "success": True,
                "pairing_code": qr_data["code"],
                "qr_code": qr_data["qr"],
                "message": "Scan QR or enter code in WhatsApp",
            }
        )
    return jsonify({"success": False, "error": "Failed to generate QR"})


@app.route("/status")
async def status_api():
    return jsonify(
        {
            "connected": bot.is_connected,
            "bot_name": bot.config["BOT_NAME"],
            "creator": bot.config["CREATOR"],
            "session_saved": os.path.exists(bot.cookies_file),
            "profile_pic": os.path.exists(bot.profile_pic_path),
            "uptime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


@app.route("/restart")
async def restart():
    global bot
    
    await bot.cleanup()
    bot = ZohaAIBot()
    await bot.setup_browser()
    return jsonify({"success": True, "message": "Bot restarted"})


# Startup
@app.before_serving
async def startup():
    # Create assets directory if not exists
    os.makedirs("assets", exist_ok=True)
    await bot.download_profile_pic()
    await bot.setup_browser()

    # Try to load session
    if await bot.load_session():
        asyncio.create_task(bot.monitor_messages())
    else:
        logger.info("⏳ Waiting for pairing...")


# Shutdown
@app.after_serving
async def shutdown():
    await bot.cleanup()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=bot.config["PORT"], debug=False)
