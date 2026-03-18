# CAD Generator

Generate 3D CAD models just by describing them in plain English.

## What it does
Type what you want, get a 3D model you can view and download.

## Supported shapes
- Box / Cube
- Cylinder
- Hollow Cylinder (Pipe / Tube)
- Sphere
- Cone
- Box with Hole

## Example prompts
- "a box 50mm wide 30mm tall 20mm deep"
- "a pipe outer diameter 30mm inner diameter 20mm height 50mm"
- "a sphere with diameter 40mm"
- "a cone base 40mm top 10mm height 60mm"

## Setup

Clone the repo and create a `.env` file with your Groq API key:
```
GROQ_API_KEY=your_key_here
```

Install and run:
```
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Stack
Python, FastAPI, CadQuery, Groq, Google model-viewer