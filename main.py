from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timezone, timedelta
import telegram
import logging
import time

# ----- Все переменные с данными -----

BOT_TOKEN = "7804555297:AAH7YFsNeJeSo5-fyVWybbAjut6VSnF96Sw"

LOGIN_CREDENTIALS = {
    "TANDOOR_MAHALLA": {
        "email": "alishermusayev1994@gmail.com",
        "password": "Lightalisher1994"
    },
    "HON_ATLAS": {
        "email": "lolaabduyusupova@gmail.com",
        "password": "a2556263"
    }
}

RESTAURANTS = [
    {
        "name": "Тандоор",
        "url": "https://app.jowi.club/ru/restaurants/ef62ef82-e7a3-4909-bb8b-906257ebd17c/cashbox_report",
        "restaurant_id": "ef62ef82-e7a3-4909-bb8b-906257ebd17c",
        "login_key": "TANDOOR_MAHALLA",
        "message_thread_id": 3
    },
    {
        "name": "Махалла 90",
        "url": "https://app.jowi.club/ru/restaurants/b3732283-d47c-4dd0-aa63-cd4bc7e0dfe3/cashbox_report",
        "restaurant_id": "b3732283-d47c-4dd0-aa63-cd4bc7e0dfe3",
        "login_key": "TANDOOR_MAHALLA",
        "message_thread_id": 7
    },
    {
        "name": "Хон Атлас",
        "url": "https://app.jowi.club/ru/restaurants/6d7d2a7a-22cd-48ed-8c43-7e944afebc4b/cashbox_report",
        "restaurant_id": "6d7d2a7a-22cd-48ed-8c43-7e944afebc4b",
        "login_key": "HON_ATLAS",
        "message_thread_id": 5
    }
]

CHAT_ID = "-1002709942333"   # id группы

# ----- Логирование -----
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ----- Selenium options -----
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

def format_amount(amount):
    """Форматирует сумму, заменяя точку на запятую и добавляя пробелы как разделители тысяч."""
    if not amount or amount == "0":
        return "0,00"
    amount = amount.replace(" ", "").replace(".", "").replace(",", "")
    try:
        num = float(amount)
        formatted = "{:,.2f}".format(num).replace(",", "X").replace(".", ",").replace("X", " ")
        return formatted.rstrip()
    except ValueError:
        return amount.replace(".", ",")

def login(driver, login_key):
    driver.get("https://app.jowi.club/ru/users/sign_in")
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "user_email")))
    credentials = LOGIN_CREDENTIALS[login_key]
    driver.find_element(By.ID, "user_email").send_keys(credentials["email"])
    driver.find_element(By.ID, "user_password").send_keys(credentials["password"])
    driver.find_element(By.CSS_SELECTOR, ".form_submit button").click()
    WebDriverWait(driver, 20).until(EC.url_contains("/ru"))
    time.sleep(5)

def get_cashbox_data(restaurant):
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.service import Service
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    try:
        login(driver, restaurant["login_key"])
        for attempt in range(3):
            try:
                restaurant_link = WebDriverWait(driver, 20).until(
                    EC.visibility_of_element_located((By.XPATH, f"//a[@href='/ru/restaurants/{restaurant['restaurant_id']}']"))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", restaurant_link)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", restaurant_link)
                time.sleep(2)
                break
            except Exception as e:
                time.sleep(3)
                if attempt == 2:
                    raise Exception(f"Не удалось кликнуть по элементу 'Начать работу' для {restaurant['name']} после трех попыток")
        driver.get(restaurant["url"])
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "standatr_date")))
        select_element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, "standatr_date")))
        select = Select(select_element)
        select.select_by_value("2")
        time.sleep(1)
        initial_income = driver.find_element(By.CSS_SELECTOR, ".large_cash b").text.strip()
        start_time = time.time()
        while time.time() - start_time < 40:
            current_income = driver.find_element(By.CSS_SELECTOR, ".large_cash b").text.strip()
            if current_income != initial_income and current_income != "0" and current_income != "":
                break
            time.sleep(2)
        else:
            return None, "Сумма не обновилась после выбора 'Вчера'"
        income = driver.find_element(By.CSS_SELECTOR, ".large_cash b").text.strip()
        last_updated = driver.find_element(By.CSS_SELECTOR, ".widget_last_updated i").text.replace("Обновлено в: ", "").strip()
        try:
            last_updated_time = datetime.strptime(last_updated, "%H:%M").replace(
                year=datetime.now(timezone(timedelta(hours=5))).year,
                month=datetime.now(timezone(timedelta(hours=5))).month,
                day=datetime.now(timezone(timedelta(hours=5))).day
            )
            if last_updated_time.date() < datetime.now(timezone(timedelta(hours=5))).date():
                return None, "Данные устарели"
        except ValueError as e:
            return None, f"Ошибка формата времени: {str(e)}"
        return income, None
    except Exception as e:
        logging.error(f"Ошибка в {restaurant['name']}: {str(e)}")
        return None, str(e)
    finally:
        driver.quit()

async def send_to_telegram():
    bot = telegram.Bot(token=BOT_TOKEN)
    yesterday = (datetime.now(timezone(timedelta(hours=5))) - timedelta(days=1)).strftime("%d.%m.%Y")
    for restaurant in RESTAURANTS:
        income, error = get_cashbox_data(restaurant)
        message_thread_id = restaurant["message_thread_id"]
        formatted_income = format_amount(income) if income else "0,00"
        message = f"Савдо: {yesterday}\n{restaurant['name']}\n\nСумма: {formatted_income}"
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                message_thread_id=message_thread_id
            )
            logging.info(f"Сообщение отправлено в Telegram для {restaurant['name']}: {message}")
        except Exception as e:
            logging.error(f"Ошибка отправки в Telegram для {restaurant['name']}: {str(e)}")
        print(f"Савдо: {yesterday}\n{restaurant['name']}\n\nСумма: {formatted_income}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(send_to_telegram())
