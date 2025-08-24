from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timezone, timedelta
import telegram
import logging
import time
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import asyncio

# ----- Все переменные с данными -----
BOT_TOKEN = os.environ.get('BOT_TOKEN', "7804555297:AAH7YFsNeJeSo5-fyVWybbAjut6VSnF96Sw")
GOOGLE_SHEETS_KEY = os.environ.get('GOOGLE_SHEETS_KEY', "1-JuXg-pAX1Ts-fNWE0P8V8ktAf6kcYa8wTkij9kEGYQ")

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
        "message_thread_id": 3,
        "sheet_name": "Тандоор"
    },
    {
        "name": "Махалла 90",
        "url": "https://app.jowi.club/ru/restaurants/b3732283-d47c-4dd0-aa63-cd4bc7e0dfe3/cashbox_report",
        "restaurant_id": "b3732283-d47c-4dd0-aa63-cd4bc7e0dfe3",
        "login_key": "TANDOOR_MAHALLA",
        "message_thread_id": 7,
        "sheet_name": "Махалла 90"
    },
    {
        "name": "Хон Атлас",
        "url": "https://app.jowi.club/ru/restaurants/6d7d2a7a-22cd-48ed-8c43-7e944afebc4b/cashbox_report",
        "restaurant_id": "6d7d2a7a-22cd-48ed-8c43-7e944afebc4b",
        "login_key": "HON_ATLAS",
        "message_thread_id": 5,
        "sheet_name": "Хон Атлас"
    }
]

CHAT_ID = os.environ.get('CHAT_ID', "-1002709942333")

# ----- Логирование -----
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

# ----- Selenium options -----
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

def setup_google_sheets():
    """Настройка подключения к Google Sheets"""
    try:
        service_account_json = os.environ.get('SERVICE_ACCOUNT_JSON')
        if not service_account_json:
            logging.error("SERVICE_ACCOUNT_JSON not found in environment variables")
            return None
            
        service_account_info = json.loads(service_account_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        client = gspread.authorize(creds)
        
        spreadsheet = client.open_by_key(GOOGLE_SHEETS_KEY)
        worksheet = spreadsheet.worksheet("Продажа")
        
        logging.info("✅ Успешное подключение к Google Sheets")
        return worksheet
        
    except Exception as e:
        logging.error(f"❌ Ошибка подключения к Google Sheets: {str(e)}")
        return None

def write_to_google_sheets(worksheet, date, restaurant_name, amount):
    """Запись данных в Google Sheets"""
    try:
        if not amount or amount == "0":
            logging.warning(f"Пустая сумма для {restaurant_name}, пропускаем запись")
            return False
            
        # Очистка суммы: убираем пробелы и заменяем запятые на точки
        clean_amount = amount.replace(" ", "").replace(",", ".")
        
        # Проверяем, что это число
        try:
            float(clean_amount)
        except ValueError:
            logging.error(f"Некорректная сумма: {amount}")
            return False
        
        # Подготовка данных для записи
        row_data = [date, restaurant_name, "Савдо", clean_amount]
        
        # Добавление новой строки
        worksheet.append_row(row_data)
        
        logging.info(f"📊 Данные записаны в Google Sheets: {restaurant_name} - {clean_amount}")
        return True
        
    except Exception as e:
        logging.error(f"❌ Ошибка записи в Google Sheets: {str(e)}")
        return False

def format_amount(amount):
    """Форматирует сумму с разделителями тысяч"""
    if not amount or amount == "0":
        return "0,00"
    
    # Очищаем от лишних символов
    amount = amount.replace(" ", "").replace(".", "").replace(",", "")
    
    try:
        num = float(amount)
        formatted = "{:,.2f}".format(num).replace(",", "X").replace(".", ",").replace("X", " ")
        return formatted.rstrip()
    except ValueError:
        return amount

def login(driver, login_key):
    """Авторизация в системе"""
    try:
        driver.get("https://app.jowi.club/ru/users/sign_in")
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "user_email")))
        
        credentials = LOGIN_CREDENTIALS[login_key]
        driver.find_element(By.ID, "user_email").send_keys(credentials["email"])
        driver.find_element(By.ID, "user_password").send_keys(credentials["password"])
        driver.find_element(By.CSS_SELECTOR, ".form_submit button").click()
        
        WebDriverWait(driver, 20).until(EC.url_contains("/ru"))
        time.sleep(3)
        return True
        
    except Exception as e:
        logging.error(f"❌ Ошибка авторизации: {str(e)}")
        return False

def get_cashbox_data(restaurant):
    """Получение данных о продажах"""
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.service import Service
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    try:
        # Авторизация
        if not login(driver, restaurant["login_key"]):
            return None, "Ошибка авторизации"
        
        # Переход к ресторану
        for attempt in range(3):
            try:
                restaurant_link = WebDriverWait(driver, 20).until(
                    EC.visibility_of_element_located((By.XPATH, f"//a[@href='/ru/restaurants/{restaurant['restaurant_id']}']"))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", restaurant_link)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", restaurant_link)
                time.sleep(2)
                break
            except Exception as e:
                if attempt == 2:
                    raise Exception(f"Не удалось перейти к ресторану {restaurant['name']}")
                time.sleep(3)
        
        # Переход к отчету кассы
        driver.get(restaurant["url"])
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "standatr_date")))
        
        # Выбор периода "Вчера"
        select_element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, "standatr_date")))
        select = Select(select_element)
        select.select_by_value("2")
        time.sleep(2)
        
        # Ожидание обновления данных
        initial_income = driver.find_element(By.CSS_SELECTOR, ".large_cash b").text.strip()
        start_time = time.time()
        
        while time.time() - start_time < 30:
            current_income = driver.find_element(By.CSS_SELECTOR, ".large_cash b").text.strip()
            if current_income != initial_income and current_income != "0" and current_income != "":
                break
            time.sleep(2)
        else:
            return None, "Сумма не обновилась после выбора 'Вчера'"
        
        # Получение итоговой суммы
        income = driver.find_element(By.CSS_SELECTOR, ".large_cash b").text.strip()
        
        # Проверка актуальности данных
        try:
            last_updated = driver.find_element(By.CSS_SELECTOR, ".widget_last_updated i").text.replace("Обновлено в: ", "").strip()
            last_updated_time = datetime.strptime(last_updated, "%H:%M").replace(
                year=datetime.now(timezone(timedelta(hours=5))).year,
                month=datetime.now(timezone(timedelta(hours=5))).month,
                day=datetime.now(timezone(timedelta(hours=5))).day
            )
            
            if last_updated_time.date() < datetime.now(timezone(timedelta(hours=5))).date():
                return None, "Данные устарели"
                
        except Exception as time_error:
            logging.warning(f"Не удалось проверить время обновления: {time_error}")
        
        return income, None
        
    except Exception as e:
        logging.error(f"❌ Ошибка в {restaurant['name']}: {str(e)}")
        return None, str(e)
        
    finally:
        driver.quit()

async def send_to_telegram():
    """Основная функция отправки данных"""
    try:
        bot = telegram.Bot(token=BOT_TOKEN)
        tz = timezone(timedelta(hours=5))
        yesterday = (datetime.now(tz) - timedelta(days=1)).strftime("%d.%m.%Y")
        
        # Настройка Google Sheets
        worksheet = setup_google_sheets()
        if not worksheet:
            logging.error("Не удалось подключиться к Google Sheets, продолжаем без записи")
        
        results = []
        
        for restaurant in RESTAURANTS:
            logging.info(f"🔄 Обработка: {restaurant['name']}")
            
            income, error = get_cashbox_data(restaurant)
            message_thread_id = restaurant["message_thread_id"]
            
            if error:
                formatted_income = "0,00"
                message = f"❌ Ошибка: {restaurant['name']}\n\nПричина: {error}"
                logging.error(f"Ошибка для {restaurant['name']}: {error}")
            else:
                formatted_income = format_amount(income)
                message = f"✅ Савдо: {yesterday}\n{restaurant['name']}\n\nСумма: {formatted_income}"
                logging.info(f"Успешно: {restaurant['name']} - {formatted_income}")
            
            # Отправка в Telegram
            try:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text=message,
                    message_thread_id=message_thread_id,
                    parse_mode='HTML'
                )
                logging.info(f"📨 Сообщение отправлено в Telegram для {restaurant['name']}")
            except Exception as e:
                logging.error(f"❌ Ошибка отправки в Telegram для {restaurant['name']}: {str(e)}")
            
            # Запись в Google Sheets
            if income and worksheet and not error:
                success = write_to_google_sheets(
                    worksheet, 
                    yesterday, 
                    restaurant["sheet_name"], 
                    income
                )
                if success:
                    results.append(f"✅ {restaurant['name']}: {formatted_income}")
                else:
                    results.append(f"❌ {restaurant['name']}: ошибка записи")
            else:
                results.append(f"⚠️ {restaurant['name']}: нет данных")
            
            # Пауза между запросами
            time.sleep(2)
        
        # Итоговый отчет
        logging.info("=" * 50)
        logging.info("ИТОГ ВЫПОЛНЕНИЯ:")
        for result in results:
            logging.info(result)
        logging.info("=" * 50)
        
    except Exception as e:
        logging.error(f"❌ Критическая ошибка в основной функции: {str(e)}")

if __name__ == "__main__":
    logging.info("🚀 Запуск бота...")
    asyncio.run(send_to_telegram())
    logging.info("🏁 Завершение работы бота")
