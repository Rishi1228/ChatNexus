import time
import os
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import google.generativeai as genai

REPLY_LOG_FILE = "reply_log.json"
GOOGLE_API_KEY = "AIzaSyB7FYh9SnzpcuzJ-cwNRBXBpzVekptL2zw"

def choose_profile_path():
    print("Which WhatsApp account do you want to use?")
    print("1. Your Account")
    print("2. Dad's Account")
    choice = input("Enter 1 or 2: ").strip()
    if choice == "1":
        return r"C:\Users\dipes\Desktop\selenium-whatsapp-profile"
    elif choice == "2":
        return r"C:\Users\dipes\Desktop\selenium-whatsapp-profile-dad"
    else:
        print("❌ Invalid choice. Defaulting to your account.")
        return r"C:\Users\dipes\Desktop\selenium-whatsapp-profile"

def setup_driver(profile_path):
    options = Options()
    options.add_argument(f"--user-data-dir={profile_path}")
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(options=options)
    driver.get("https://web.whatsapp.com")
    return driver

def wait_for_whatsapp(driver):
    print("⏳ Waiting for WhatsApp Web to load...")
    WebDriverWait(driver, 180).until(
        EC.presence_of_element_located((By.XPATH, '//div[@role="textbox" and @contenteditable="true"]'))
    )
    print("✅ WhatsApp Web is loaded")

def open_chat(driver, chat_name):
    print(f"🔍 Searching for chat: {chat_name}")
    try:
        search_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//div[@aria-label="Search input textbox"]'))
        )
        search_input.click()
        time.sleep(1)
        search_input.send_keys(Keys.CONTROL + "a")
        search_input.send_keys(Keys.BACKSPACE)
        time.sleep(0.5)
        for char in chat_name:
            search_input.send_keys(char)
            time.sleep(0.05)
        time.sleep(1.5)
        chat = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, f'//span[@title="{chat_name}"]'))
        )
        chat.click()
        print(f"✅ Chat '{chat_name}' opened.")
        return True
    except Exception as e:
        print("❌ Could not open chat.")
        print("Error:", e)
        return False

def get_today_messages(driver):
    messages = driver.find_elements(By.XPATH, '//div[@data-pre-plain-text]')
    results = []
    for msg in messages:
        try:
            pre = msg.get_attribute("data-pre-plain-text")
            if not pre:
                continue
            try:
                timestamp_str = pre.split(",")[1].split("]")[0].strip()
                msg_date = datetime.strptime(timestamp_str, "%d/%m/%Y").date()
                if msg_date != datetime.today().date():
                    continue
            except Exception:
                continue
            try:
                read_more = msg.find_element(By.CLASS_NAME, 'read-more-button')
                driver.execute_script("arguments[0].click();", read_more)
                time.sleep(0.2)
            except:
                pass
            text_elems = msg.find_elements(By.XPATH, './/span[contains(@class,"selectable-text")]')
            text = "\n".join([t.text.strip() for t in text_elems if t.text.strip()])
            if text:
                results.append(text)
        except Exception:
            continue
    return results

def send_message(driver, message_text):
    try:
        input_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//div[@role="textbox" and @contenteditable="true" and @data-tab="10"]'))
        )
        input_box.click()
        time.sleep(1)
        actions = ActionChains(driver)
        for line in message_text.split("\n"):
            actions.send_keys(line)
            actions.key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT)
        actions.send_keys(Keys.ENTER)
        actions.perform()
        print(f"📤 Sent message:\n{message_text}")
    except Exception as e:
        print("❌ Failed to send message:", e)

def is_rate_query(message):
    keywords = [
        "rate", "price", "tmt", "bar", "angle", "rod", "pipe", "channel", "flat", "tee", "square", "sq", "round", "rd"
    ]
    msg = message.lower()
    return any(k in msg for k in keywords)

def collect_all_rates(driver, group_names):
    all_rates = {}
    for group in group_names:
        print(f"Opening chat: {group}")
        opened = open_chat(driver, group)
        if not opened:
            print(f"❌ Could not open chat: {group}")
            all_rates[group] = []
            continue
        time.sleep(2)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, '//div[@data-pre-plain-text]'))
            )
        except Exception:
            print(f"❌ Could not find any messages for group: {group}")
            all_rates[group] = []
            continue
        for _ in range(5):
            try:
                msg_elem = driver.find_element(By.XPATH, '//div[@data-pre-plain-text]')
                driver.execute_script("arguments[0].scrollTop = 0;", msg_elem)
                time.sleep(1)
            except Exception:
                break
        msgs = get_today_messages(driver)
        all_rates[group] = msgs
        print(f"Collected from {group}:")
        for msg in msgs:
            print(msg)
    return all_rates

def reply_with_all_rates(driver, all_rates, query):
    answer = ask_gemini_for_rate(query, all_rates)
    try:
        outgoing_msgs = driver.find_elements(By.XPATH, '//div[contains(@class,"message-out")]//span[contains(@class,"selectable-text")]')
        last_sent = outgoing_msgs[-1].text.strip() if outgoing_msgs else ""
    except Exception:
        last_sent = ""
    if last_sent == answer:
        print("⚠️ Duplicate answer detected, not sending the same message again.")
        return
    send_message(driver, answer)

def get_unread_chats(driver):
    unread_chats = []
    chat_elems = driver.find_elements(By.XPATH, "//div[contains(@class, '_ak8i')]//span[@data-testid='icon-unread-count']")
    print(f"Found {len(chat_elems)} unread indicators in chat list.")
    for elem in chat_elems:
        try:
            chat_row = elem.find_element(By.XPATH, './../..')
            chat_name_elem = chat_row.find_element(By.XPATH, ".//span[@dir='auto' and @title]")
            chat_name = chat_name_elem.get_attribute("title")
            print(f"Unread chat detected: {chat_name}")
            unread_chats.append(chat_name)
        except Exception:
            continue
    print(f"All unread chats: {unread_chats}")
    return unread_chats

def get_new_messages(driver, chat_name, last_replied_msg):
    open_chat(driver, chat_name)
    time.sleep(1)
    messages = get_today_messages(driver)
    if not messages:
        return []
    if last_replied_msg and last_replied_msg in messages:
        idx = messages.index(last_replied_msg)
        return messages[idx+1:]
    return messages

def load_reply_log():
    if os.path.exists(REPLY_LOG_FILE):
        with open(REPLY_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_reply_log(log):
    with open(REPLY_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def ask_gemini_for_rate(query, all_rates):
    prompt = (
        "You are a helpful assistant for extracting steel rates from WhatsApp group messages.\n"
        "Below are all messages sent today, grouped by company. Each company's messages are under its name.\n\n"
        "IMPORTANT:\n"
        "- Sometimes, a company will send a rate message, and then send a correction or update (e.g., 'rates increased by 100') in a separate message.\n"
        "- If you see a correction/update message after a rate message from the same company, apply the correction to the previous rate(s) for that company.\n"
        "- Always use the latest/most updated rate for each item, considering any corrections or changes mentioned in later messages.\n"
        "- Extract and reply with only the relevant rate(s) for the item(s) mentioned in the user's query, showing the rate from every company that mentions it.\n"
        "- For each company, also include any relevant specifications (such as loading charges, delivery charges, payment terms, or other conditions) that are mentioned in the company's messages and are related to the query.\n"
        "- Format your answer as:\n"
        "Company Name: [rate line]\n"
        "[specifications if any]\n"
        "(Leave a blank line between each company's reply.)\n"
        "- If a company does not mention the item, do not include it in your answer.\n"
        "- If no company mentions the item, reply with 'Not found'.\n\n"
    )
    for group, messages in all_rates.items():
        prompt += f"Company: {group}\n"
        for msg in messages:
            prompt += f"- {msg}\n"
        prompt += "\n"
    prompt += f"User query: {query}\n"
    print("==== GEMINI PROMPT ====")
    print(prompt)
    print("=======================")
    response = model.generate_content(prompt)
    return response.text.strip()

def auto_reply_loop(driver, all_rates):
    reply_log = load_reply_log()
    print("🤖 Smart auto-reply bot started. Press Ctrl+C to stop.")
    while True:
        unread_chats = get_unread_chats(driver)
        for chat_name in unread_chats:
            last_replied_msg = reply_log.get(chat_name, "")
            new_msgs = get_new_messages(driver, chat_name, last_replied_msg)
            if not new_msgs:
                continue
            last_msg = new_msgs[-1]
            if is_rate_query(last_msg):
                reply_with_all_rates(driver, all_rates, last_msg)
                reply_log[chat_name] = last_msg
                save_reply_log(reply_log)
        time.sleep(10)

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

if __name__ == "__main__":
    profile_path = choose_profile_path()
    os.makedirs(profile_path, exist_ok=True)
    driver = setup_driver(profile_path)
    wait_for_whatsapp(driver)

    recieves = ['G. G.(SRMM) RATES UPDATES', 'CHAMPION ROLLING MILL PVT', 'MULTI STEEL RATE']
    sends = ['Rishi Shah', 'Nirali', 'Asha', 'Hinal', 'Dipesh - Hinal']

    all_rates = collect_all_rates(driver, recieves)
    auto_reply_loop(driver, all_rates)
    driver.quit()

