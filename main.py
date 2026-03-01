import telebot
from telebot import types
import pandas as pd
import random
import os
import sqlite3
import time
import threading
import requests
from flask import Flask

# ==========================================
#              SOZLAMALAR
# ==========================================
API_TOKEN = '8490998299:AAEKIQQHwFbSboUsPTiu5FpzqWRFDuldb0g'  # Tokeningiz
ADMIN_ID = 7201215484  # <-- O'zingizning ID raqamingizni yozing!
CHANNEL_USERNAME = '@Binary_Mind_Uz'
# ==========================================

bot = telebot.TeleBot(API_TOKEN)
server = Flask(__name__)
user_data = {}

# --- BAZA BILAN ISHLASH ---
def init_db():
    conn = sqlite3.connect('bot_users.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, joined_date TEXT)''')
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
        if status in ['left', 'kicked']: return False
        return True
    except: return True

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

# --- FLASK SERVER VA O'ZINI UYG'OTISH ---
@server.route('/')
def home():
    return "Bot ishlayapti! (Active)", 200

def keep_alive():
    """Render serverni uxlab qolmasligi uchun har 5 daqiqada o'ziga so'rov yuboradi"""
    while True:
        time.sleep(300) # 5 daqiqa
        try:
            # Agar botingiz Renderda bo'lsa, URL ni to'g'rilab qo'ysangiz yanada ishonchli bo'ladi
            requests.get("http://127.0.0.1:5000/") 
        except: pass

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
    bot.send_message(message.chat.id, """Assalomu alaykum!
    📊 Bot uchun Excel faylingiz quyidagi tartibda bolishi SHART:
    A ustun: Savol matni.
    B ustun: ✅ Togri javob (doim shu yerga yoziladi).
    C, D, E... ustunlar: ❌ Notogri javob variantlari.
    Namuna:
    | A (Savol) | B (To‘g‘ri) | C (Xato) | D (Xato) |
    | :--- | :--- | :--- | :--- |
    | Uzbekiston poytaxti? | Toshkent | Samarqand | Buxoro |
    | 2 + 2 nechi? | 4 | 5 | 3 | 1 |
    | Apple asoschisi kim? | Stiv Jobs | Bill Geyts | Ilon Mask |""")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check(call):
    if check_subscription(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(call.message.chat.id, "Obuna tasdiqlandi! Excel fayl yuboring.")
    else:
        bot.answer_callback_query(call.id, "Siz hali a'zo bo'lmadingiz!", show_alert=True)

@bot.message_handler(commands=['send'])
def cmd_broadcast(message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace('/send', '').strip()
    if not text:
        bot.reply_to(message, "Matn yozing. Masalan: /send Salom")
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
            'qs': qs, 'total': len(qs), 'score': 0, 'idx': 0, 'limit': len(qs), 'timer': 15, 'ctrl_msg_id': None
        }
        
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add('10', '20', '30', '60', f'Hammasi ({len(qs)})')
        msg = bot.send_message(message.chat.id, f"Jami {len(qs)} ta savol. Nechta ishlaysiz?", reply_markup=markup)
        bot.register_next_step_handler(msg, step_limit)
        
    except Exception as e:
        bot.reply_to(message, f"Xatolik: {e}")

def step_limit(message):
    cid = message.chat.id
    if cid not in user_data: return
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
    try: user_data[cid]['timer'] = int(message.text)
    except: user_data[cid]['timer'] = 15
    
    bot.send_message(cid, "Boshladik!", reply_markup=types.ReplyKeyboardRemove())
    send_question(cid)

def send_question(cid):
    data = user_data.get(cid)
    if not data: return
    
    # Test tugadimi?
    if data['idx'] >= data['limit']:
        bot.send_message(cid, f"🏁 **Test yakunlandi!**\n\n📊 Natija: {data['score']} / {data['limit']} ({(data['score']/data['limit'])*100:.1f}%)", parse_mode="Markdown")
        del user_data[cid]
        return
        
    q = data['qs'][data['idx']]
    try:
        bot.send_poll(cid, f"{data['idx']+1}/{data['limit']}. {q['q']}", q['o'], type='quiz', 
                      correct_option_id=q['c'], open_period=data['timer'], is_anonymous=False)
        
        # Tugmalarni yuborish (Davom etish / To'xtatish)
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🟢 Davom ettirish", callback_data="next_q", style="success"),
            types.InlineKeyboardButton("🛑 To'xtatish", callback_data="stop_q", style="danger")
        )
        ctrl_msg = bot.send_message(cid, "Vaqt tugadimi yoki o'tkazib yuborasizmi?", reply_markup=markup)
        data['ctrl_msg_id'] = ctrl_msg.message_id

    except Exception as e:
        del user_data[cid]

# Foydalanuvchi javob berganda ushlab olish
@bot.poll_answer_handler()
def handle_answer(poll):
    uid = poll.user.id
    if uid not in user_data: return
    
    data = user_data[uid]
    q = data['qs'][data['idx']]
    
    if poll.option_ids[0] == q['c']:
        data['score'] += 1
    
    data['idx'] += 1
    
    # Eski boshqaruv tugmasini o'chirib tashlash
    try:
        bot.delete_message(uid, data['ctrl_msg_id'])
    except: pass
    
    send_question(uid)

# Tugmalar bosilganda (Davom etish yoki To'xtatish)
@bot.callback_query_handler(func=lambda call: call.data in ["next_q", "stop_q"])
def handle_buttons(call):
    cid = call.message.chat.id
    if cid not in user_data:
        try: bot.delete_message(cid, call.message.message_id)
        except: pass
        return

    data = user_data[cid]
    
    if call.data == "stop_q":
        # Testni to'xtatish
        try: bot.delete_message(cid, call.message.message_id)
        except: pass
        
        ishlangan_savollar = data['idx'] # Nechta savol ko'rsatilgani
        bot.send_message(cid, f"🛑 **Test to'xtatildi!**\n\nSiz ishlagan savollar: {ishlangan_savollar} ta\n✅ To'g'ri javoblar: {data['score']}", parse_mode="Markdown")
        del user_data[cid]
        
    elif call.data == "next_q":
        # Bitta savolni o'tkazib yuborish (vaqt tugaganda yoki javob bermaganda)
        try: bot.delete_message(cid, call.message.message_id)
        except: pass
        data['idx'] += 1
        send_question(cid)

# --- ISHGA TUSHIRISH (MAIN) ---
if __name__ == "__main__":
    init_db()
    
    # 1. Eski webhooklarni tozalash (Xatolik bermasligi uchun)
    try: bot.remove_webhook(); time.sleep(1)
    except: pass

    # 2. O'zini uyg'oq saqlash tizimi
    t_keep_alive = threading.Thread(target=keep_alive, daemon=True)
    t_keep_alive.start()

    # 3. Botni ishga tushirish
    bot_thread = threading.Thread(target=bot.infinity_polling, kwargs={'timeout': 10, 'long_polling_timeout': 5})
    bot_thread.start()
    
    # 4. Flask Web Server
    port = int(os.environ.get("PORT", 5000))
    server.run(host="0.0.0.0", port=port)