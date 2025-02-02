import logging
import aiohttp
import asyncio

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Replace with your tokens
API_TOKEN = "nope"
OPENWEATHER_API_KEY = "nope"

# Initialize bot and dispatcher with memory storage
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# In-memory persistent user profiles
user_profiles = {}  


async def get_weather_temp(city: str) -> float:
    """
    Get current temperature (in °C) for a given city from OpenWeatherMap.
    """
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Error fetching weather for {city}: {response.status}")
                    return None
                data = await response.json()
                return data["main"]["temp"]
    except Exception as e:
        logging.error(f"Exception in get_weather_temp: {e}")
        return None

async def get_food_info(product_name: str):
    """
    Fetch calorie information for a product using the OpenFoodFacts API.
    """
    url = f"https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={product_name}&json=true"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Error fetching food info for {product_name}: {response.status}")
                    return None
                data = await response.json()
                products = data.get('products', [])
                if products:
                    first_product = products[0]
                    return {
                        'name': first_product.get('product_name', 'Unknown'),
                        'calories': first_product.get('nutriments', {}).get('energy-kcal_100g', 0)
                    }
                return None
    except Exception as e:
        logging.error(f"Exception in get_food_info: {e}")
        return None


def calculate_water_goal(weight: float, activity_minutes: int, temperature: float = 20.0) -> int:
    """
    Calculate water goal in ml based on weight, activity, and ambient temperature.
    """
    base = weight * 30
    extra_for_activity = (activity_minutes // 30) * 500
    extra_for_heat = 500 if temperature > 25 else 0
    return int(base + extra_for_activity + extra_for_heat)

def calculate_calorie_goal(weight: float, height: float, age: int, activity_minutes: int) -> int:
    """
    Calculate daily calorie goal based on BMR and activity level.
    """
    bmr = (10 * weight) + (6.25 * height) - (5 * age)
    extra_activity = 400 if activity_minutes > 60 else (200 if activity_minutes > 30 else 0)
    return int(bmr + extra_activity)


def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Set Profile")],
            [KeyboardButton(text="Log Water")],
            [KeyboardButton(text="Log Food")],
            [KeyboardButton(text="Check Food Info")],
            [KeyboardButton(text="Check Progress")],
        ],
        resize_keyboard=True,
    )

class ProfileStates(StatesGroup):
    weight = State()
    height = State()
    age = State()
    activity = State()
    city = State()

class LogWaterStates(StatesGroup):
    amount = State()

class LogFoodStates(StatesGroup):
    food_name = State()
    food_amount = State()

class FoodInfoStates(StatesGroup):
    food_name = State()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """
    Start the bot and display the main menu.
    """
    await message.answer(
        "Welcome! Use the buttons below to interact with the bot.",
        reply_markup=get_main_menu(),
    )

@dp.message(F.text == "Set Profile")
async def cmd_set_profile(message: types.Message, state: FSMContext):
    """
    Initiate the profile setup conversation.
    """
    await state.clear()  # Clear any previous conversation state
    await state.set_state(ProfileStates.weight)
    await message.answer("Enter your weight (kg):", reply_markup=ReplyKeyboardRemove())

@dp.message(ProfileStates.weight)
async def process_weight(message: types.Message, state: FSMContext):
    try:
        weight = float(message.text)
        await state.update_data(weight=weight)
        await state.set_state(ProfileStates.height)
        await message.answer("Enter your height (cm):")
    except ValueError:
        await message.answer("Please enter a valid weight in kg (e.g., 70).")

@dp.message(ProfileStates.height)
async def process_height(message: types.Message, state: FSMContext):
    try:
        height = float(message.text)
        await state.update_data(height=height)
        await state.set_state(ProfileStates.age)
        await message.answer("Enter your age:")
    except ValueError:
        await message.answer("Please enter a valid height in cm (e.g., 170).")

@dp.message(ProfileStates.age)
async def process_age(message: types.Message, state: FSMContext):
    try:
        age = int(message.text)
        await state.update_data(age=age)
        await state.set_state(ProfileStates.activity)
        await message.answer("How many minutes of activity do you have per day?")
    except ValueError:
        await message.answer("Please enter a valid age (e.g., 30).")

@dp.message(ProfileStates.activity)
async def process_activity(message: types.Message, state: FSMContext):
    try:
        activity = int(message.text)
        await state.update_data(activity=activity)
        await state.set_state(ProfileStates.city)
        await message.answer("Which city do you live in?")
    except ValueError:
        await message.answer("Please enter a valid number for activity minutes (e.g., 45).")

@dp.message(ProfileStates.city)
async def process_city(message: types.Message, state: FSMContext):
    city = message.text
    data = await state.get_data()
    weight = data.get("weight")
    height = data.get("height")
    age = data.get("age")
    activity = data.get("activity")
    
    # Get current temperature for the city
    temp = await get_weather_temp(city) or 20.0
    water_goal = calculate_water_goal(weight, activity, temp)
    calorie_goal = calculate_calorie_goal(weight, height, age, activity)
    
    # Save user profile data persistently
    user_profiles[message.from_user.id] = {
        "weight": weight,
        "height": height,
        "age": age,
        "activity": activity,
        "city": city,
        "temperature": temp,
        "water_goal": water_goal,
        "calorie_goal": calorie_goal,
        "logged_water": 0,
        "logged_calories": 0,
        "burned_calories": 0,
    }
    
    await state.clear()
    await message.answer(
        f"Profile set!\n\n"
        f"Weight: {weight} kg\n"
        f"Height: {height} cm\n"
        f"Age: {age}\n"
        f"Activity: {activity} min/day\n"
        f"City: {city}\n"
        f"Temperature: {temp}°C\n\n"
        f"Your daily goals:\n"
        f"Water: {water_goal} ml/day\n"
        f"Calories: {calorie_goal} kcal/day",
        reply_markup=get_main_menu(),
    )

@dp.message(F.text == "Log Water")
async def cmd_log_water(message: types.Message, state: FSMContext):
    user_profile = user_profiles.get(message.from_user.id)
    if not user_profile:
        await message.answer("Please set your profile first using the 'Set Profile' button.", reply_markup=get_main_menu())
        return
    await state.set_state(LogWaterStates.amount)
    await message.answer("How many milliliters of water did you drink?", reply_markup=ReplyKeyboardRemove())

@dp.message(LogWaterStates.amount)
async def process_log_water(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_profile = user_profiles.get(user_id)
    if not user_profile:
        await state.clear()
        await message.answer("Please set your profile first.", reply_markup=get_main_menu())
        return
    try:
        amount = int(message.text)
        user_profile["logged_water"] += amount
        current = user_profile["logged_water"]
        goal = user_profile["water_goal"]
        remaining = max(goal - current, 0)
        await state.clear()
        if remaining <= 0:
            await message.answer(f"Great! You've reached your water goal: {current} ml.", reply_markup=get_main_menu())
        else:
            await message.answer(f"Logged: {amount} ml. Remaining: {remaining} ml.", reply_markup=get_main_menu())
    except ValueError:
        await message.answer("Please enter a valid number (e.g., 250).")

@dp.message(F.text == "Log Food")
async def cmd_log_food(message: types.Message, state: FSMContext):
    user_profile = user_profiles.get(message.from_user.id)
    if not user_profile:
        await message.answer("Please set your profile first using the 'Set Profile' button.", reply_markup=get_main_menu())
        return
    await state.set_state(LogFoodStates.food_name)
    await message.answer("Enter the name of the food you'd like to log:", reply_markup=ReplyKeyboardRemove())

@dp.message(LogFoodStates.food_name)
async def process_log_food_name(message: types.Message, state: FSMContext):
    food_info = await get_food_info(message.text)
    if food_info:
        await state.update_data(current_food=food_info)
        await state.set_state(LogFoodStates.food_amount)
        await message.answer(
            f"Found: {food_info['name']}\n"
            f"Calories per 100g: {food_info['calories']} kcal.\n"
            f"How many grams did you consume?"
        )
    else:
        await message.answer("Could not find information about this food. Try another name.")

@dp.message(LogFoodStates.food_amount)
async def process_log_food_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        data = await state.get_data()
        food_info = data.get("current_food")
        if not food_info:
            await state.clear()
            await message.answer("Something went wrong. Please try again.", reply_markup=get_main_menu())
            return
        calories_per_100g = food_info["calories"]
        total_calories = (calories_per_100g / 100) * amount
        user_profiles[message.from_user.id]["logged_calories"] += total_calories
        await state.clear()
        await message.answer(
            f"Logged: {food_info['name']} ({amount}g)\n"
            f"Total Calories: {total_calories:.1f} kcal.\n"
            f"Your updated total: {user_profiles[message.from_user.id]['logged_calories']:.1f} kcal.",
            reply_markup=get_main_menu()
        )
    except ValueError:
        await message.answer("Please enter a valid number (e.g., 150).")

@dp.message(F.text == "Check Progress")
async def cmd_check_progress(message: types.Message):
    user_profile = user_profiles.get(message.from_user.id)
    if not user_profile:
        await message.answer("Please set your profile first using the 'Set Profile' button.", reply_markup=get_main_menu())
        return
    text = (
        f"Progress:\n\n"
        f"Water:\n"
        f"Consumed: {user_profile['logged_water']} ml / {user_profile['water_goal']} ml\n\n"
        f"Calories:\n"
        f"Consumed: {user_profile['logged_calories']:.1f} kcal / {user_profile['calorie_goal']} kcal\n"
        f"Burned: {user_profile['burned_calories']:.1f} kcal"
    )
    await message.answer(text, reply_markup=get_main_menu())


@dp.message(F.text == "Check Food Info")
async def cmd_check_food_info(message: types.Message, state: FSMContext):
    await state.set_state(FoodInfoStates.food_name)
    await message.answer("Enter the name of the food you'd like to check:", reply_markup=ReplyKeyboardRemove())

@dp.message(FoodInfoStates.food_name)
async def process_food_info(message: types.Message, state: FSMContext):
    food_info = await get_food_info(message.text)
    await state.clear()
    if food_info:
        await message.answer(
            f"Product: {food_info['name']}\n"
            f"Calories per 100g: {food_info['calories']} kcal.",
            reply_markup=get_main_menu()
        )
    else:
        await message.answer(
            "Could not find information about this product. Try another name.",
            reply_markup=get_main_menu()
        )

@dp.message()
async def fallback_handler(message: types.Message):
    await message.answer(
        "I didn't understand that. Use the buttons to interact with the bot.",
        reply_markup=get_main_menu()
    )

async def main():
    logging.info("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
