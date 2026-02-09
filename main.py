import telebot
from telebot import types
import pandas as pd
import random
import os
import sqlite3
import time
import threading
from flask import Flask, request

# ==========================================
#              SOZLAMALAR
# ==========================================
API_TOKEN = '8490998299:AAEKIQQHwFbSboUsPTiu5FpzqWRFDuldb0g'  # <-- O'zgartiring
ADMIN_ID = 7201215484  # <-- O'z ID raqamingizni yozing (faqat raqam)
CHANNEL_USERNAME = '@Binary_Mind_Uz'  # <-- Majburiy obuna kanali
# ==========================================

bot = telebot.TeleBot(API_TOKEN)
server = Flask(__name__)
user_data = {}

# --- BAZA BILAN ISHLASH (SQLite) ---
def init_db():
    # check_same_thread=False bu Flask va Bot bir vaqtda ishlaganda xato bermasligi uchun kerak
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            joined_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_user_to_db(user_id):
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO users (user_id, joined_date) VALUES (?, datetime('now'))", (user_id,))
        conn.commit()
    except: pass
    conn.close()

def get_all_users():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# --- YORDAMCHI FUNKSIYALAR ---
def check_subscription(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        if status in ['left', 'kicked']:
            return False
        return True
    except:
        return True # Xato bo'lsa (masalan admin bo'lmasangiz) o'tkazib yuboradi

def read_excel_quiz(file_path):
    try:
        df = pd.read_excel(file_path, header=None)
        questions = []
        for index, row in df.iterrows():
            row = row.dropna()
            if len(row) < 2: continue
            
            q_text = str(row[0])
            correct = str(row[1])
            wrongs = [str(x) for x in row[2:].tolist()]
            
            options = [correct] + wrongs
            random.shuffle(options)
            
            try:
                c_id = options.index(correct)
                questions.append({'q': q_text, 'o': options, 'c': c_id})
            except: pass
        return questions
    except: return None

# --- FLASK SERVER (RENDER UCHUN) ---
@server.route('/')
def home():
    return "Bot ishlayapti! (Active)", 200

# --- BOT BUYRUQLARI ---
@bot.message_handler(commands=['start'])
def cmd_start(message):
    add_user_to_db(message.from_user.id)
    
    if not check_subscription(message.from_user.id):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Kanalga a'zo bo'lish", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"))
        markup.add(types.InlineKeyboardButton("Tekshirish", callback_data="check_sub"))
        bot.send_message(message.chat.id, f"Botdan foydalanish uchun {CHANNEL_USERNAME} ga a'zo bo'ling!", reply_markup=markup)
        return

    bot.send_message(message.chat.id, "Assalomu alaykum! Menga Excel fayl yuboring.")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check(call):
    if check_subscription(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "Obuna tasdiqlandi! Excel fayl yuboring.")
    else:
        bot.answer_callback_query(call.id, "Siz hali a'zo bo'lmadingiz!", show_alert=True)

@bot.message_handler(commands=['stop'])
def cmd_stop(message):
    if message.chat.id in user_data:
        del user_data[message.chat.id]
        bot.send_message(message.chat.id, "🛑 Test to'xtatildi.")
    else:
        bot.send_message(message.chat.id, "Hozir test ketmayapti.")

@bot.message_handler(commands=['send'])
def cmd_broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace('/send', '').strip()
    if not text:
        bot.reply_to(message, "Matn yozing.")
        return
    
    users = get_all_users()
    count = 0
    for user_id in users:
        try:
            bot.send_message(user_id, text)
            count += 1
            time.sleep(0.05)
        except: pass
    bot.reply_to(message, f"Xabar {count} kishiga yuborildi.")

@bot.message_handler(content_types=['document'])
def handle_file(message):
    if not check_subscription(message.from_user.id):
        bot.reply_to(message, f"Avval {CHANNEL_USERNAME} ga a'zo bo'ling!")
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        fname = f"quiz_{message.chat.id}.xlsx"
        with open(fname, 'wb') as f: f.write(downloaded)
        
        qs = read_excel_quiz(fname)
        os.remove(fname)
        
        if not qs:
            bot.reply_to(message, "Fayl xato yoki savollar yo'q.")
            return

        random.shuffle(qs)
        user_data[message.chat.id] = {
            'qs': qs, 'total': len(qs), 'score': 0, 'idx': 0, 'limit': len(qs), 'timer': 15
        }
        
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add('10', '20', '30', f'Hammasi ({len(qs)})')
        msg = bot.send_message(message.chat.id, f"Jami {len(qs)} ta savol. Nechta ishlaysiz?", reply_markup=markup)
        bot.register_next_step_handler(msg, step_limit)
        
    except Exception as e:
        bot.reply_to(message, f"Xatolik: {e}")

def step_limit(message):
    cid = message.chat.id
    if cid not in user_data: return
    if message.text == '/stop': cmd_stop(message); return

    txt = message.text
    limit = user_data[cid]['total']
    if txt.isdigit(): limit = int(txt)
    
    user_data[cid]['limit'] = min(limit, user_data[cid]['total'])
    
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add('10', '15', '30', '45')
    msg = bot.send_message(cid, "Har bir savolga necha soniya?", reply_markup=markup)
    bot.register_next_step_handler(msg, step_timer)

def step_timer(message):
    cid = message.chat.id
    if cid not in user_data: return
    if message.text == '/stop': cmd_stop(message); return
    
    try: user_data[cid]['timer'] = int(message.text)
    except: user_data[cid]['timer'] = 15
    
    bot.send_message(cid, "Boshladik! (/stop - to'xtatish)", reply_markup=types.ReplyKeyboardRemove())
    send_question(cid)

def send_question(cid):
    data = user_data.get(cid)
    if not data: return
    
    if data['idx'] >= data['limit']:
        bot.send_message(cid, f"🏁 Tugadi!\nNatija: {data['score']} / {data['limit']}")
        del user_data[cid]
        return
        
    q = data['qs'][data['idx']]
    try:
        bot.send_poll(cid, f"{data['idx']+1}. {q['q']}", q['o'], type='quiz', 
                      correct_option_id=q['c'], open_period=data['timer'], is_anonymous=False)
    except:
        del user_data[cid] # Bot bloklansa ma'lumotni o'chirish

@bot.poll_answer_handler()
def handle_answer(poll):
    uid = poll.user.id
    if uid not in user_data: return
    
    data = user_data[uid]
    q = data['qs'][data['idx']]
    
    if poll.option_ids[0] == q['c']:
        data['score'] += 1
    
    data['idx'] += 1
    send_question(uid)

# --- ISHGA TUSHIRISH (MAIN) ---
if __name__ == "__main__":
    init_db()
    
    # 1. ESKI WEBHOOKNI O'CHIRISH (MUHIM!)
    print("Eski webhook tozalanmoqda...")
    try:
        bot.remove_webhook()
        time.sleep(1) # 1 soniya kutamiz
    except Exception as e:
        print(f"Webhook o'chirishda xato (zararsiz): {e}")

    # 2. Botni alohida potokda ishlatamiz
    print("Bot polling rejimida ishga tushmoqda...")
    bot_thread = threading.Thread(target=bot.infinity_polling)
    bot_thread.start()
    
    # 3. Flask serverni ishlatamiz (Render shu portni tinglaydi)
    print("Flask Server ishga tushdi...")
    port = int(os.environ.get("PORT", 5000))
    server.run(host="0.0.0.0", port=port)