import csv
import httpx
import cachetools
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
import os

app = FastAPI()

# 设置模板文件夹路径
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Open-Meteo API的基URL
BASE_URL = "https://api.open-meteo.com/v1/forecast"

# 存储城市信息
cities = []

# 加载城市数据
def load_cities(filepath: str):
    global cities
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                country = row["country"]
                capital = row["capital"]
                latitude = float(row["latitude"])
                longitude = float(row["longitude"])

                # 存储到城市列表
                cities.append({
                    "country": country,
                    "capital": capital,
                    "latitude": latitude,
                    "longitude": longitude
                })
    except FileNotFoundError:
        print(f"File {filepath} not found. Starting with an empty city list.")
    except Exception as e:
        print(f"Error loading cities: {e}")

# 保存城市数据到文件
def save_cities(filepath: str):
    with open(filepath, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=["country", "capital", "latitude", "longitude"])
        writer.writeheader()
        for city in cities:
            writer.writerow(city)

# 启动时加载城市数据
load_cities("europe.csv")

# 获取天气数据的函数
weather_cache = cachetools.LRUCache(maxsize=100)  # 缓存最大 100 个城市的天气数据

async def get_weather(city_name: str, latitude: float, longitude: float):
    if city_name in weather_cache:
        return weather_cache[city_name]  # 如果缓存中有数据，直接返回
    
    # 没有缓存数据时，去请求 API
    async with httpx.AsyncClient() as client:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m",
            "temperature_unit": "celsius",
            "timezone": "Europe/Madrid"
        }
        response = await client.get(BASE_URL, params=params, timeout=30.0)
        data = response.json()
        weather_cache[city_name] = data['hourly']['temperature_2m'][0]  # 将数据存入缓存
        return weather_cache[city_name]

# 主页路由
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# 查看所有城市
@app.get("/cities")
def get_cities():
    return cities

# 添加城市
@app.post("/cities")
def add_city(city: dict):
    cities.append(city)
    save_cities("europe.csv")  # 添加城市后保存到文件
    return {"message": "City added successfully!"}

# 删除城市
@app.delete("/cities/{country_name}")
def delete_city(country_name: str):
    global cities
    # 找到对应国家的城市并删除
    city_to_delete = next((city for city in cities if city["country"].lower() == country_name.lower()), None)
    
    if city_to_delete:
        cities = [city for city in cities if city["country"].lower() != country_name.lower()]
        save_cities("europe.csv")  # 删除城市后保存到文件
        return {"message": f"City from {country_name} deleted successfully!"}
    else:
        raise HTTPException(status_code=404, detail=f"City with country {country_name} not found")

# 更新所有城市的天气信息
@app.get("/update")
async def update_weather():
    weather_data = {}
    for city in cities:
        city_name = city["country"]
        try:
            temperature = await get_weather(city_name, city["latitude"], city["longitude"])
            if temperature is not None:
                weather_data[city_name] = round(temperature, 2)
            else:
                weather_data[city_name] = "Data not available"
        except httpx.ConnectTimeout:
            weather_data[city_name] = "Request timed out"
        except Exception as e:
            weather_data[city_name] = f"Error: {str(e)}"
    
    return JSONResponse(content=weather_data)
