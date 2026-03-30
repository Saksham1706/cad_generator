# CAD Generator

Generate 3D CAD models just by describing them in plain English.

## What it does
Type what you want, get a 3D model you can view and download.

## Supported shapes & features
- Box / Cube
- Cylinder
- Hollow Cylinder (Pipe / Tube)
- Sphere
- Cone
- **Holes:** Circular and Square (on any face)
- **Edge Treatments:** Fillets (Rounded) and Chamfers (Beveled)
- **Text:** Embossing (Raised) and Engraving (Cut)

## Example prompts
- "a box 50mm wide 30mm tall 20mm deep"
- "a pipe outer diameter 30mm inner diameter 20mm height 50mm"
- "A box 100mm wide, 100mm deep, and 20mm tall. Engrave the name 'CHRISTOPHER' 3mm deep into the top face."
- "A box 80mm wide, 80mm deep, and 30mm tall. Put a 20mm square hole 10mm deep on the top face, a 15mm circular hole 10mm deep on the front face, engrave 'DEV' on the right face, and fillet the edges by 2mm."

## Setup

Clone the repo and create a `.env` file with your Groq API key:
```text
GROQ_API_KEY=your_key_here
