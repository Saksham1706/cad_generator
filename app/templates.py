TEMPLATES = [
    {
        "category": "Basics",
        "items": [
            {"label": "Simple Box", "prompt": "a box 50mm wide 30mm tall 20mm deep"},
            {"label": "Cylinder Rod", "prompt": "a cylinder 20mm diameter and 80mm tall"},
            {"label": "Pipe / Tube", "prompt": "a pipe outer diameter 30mm inner diameter 20mm height 50mm"},
            {"label": "Sphere", "prompt": "a sphere 40mm in diameter"},
            {"label": "Dome", "prompt": "a hemisphere dome 50mm in diameter"},
        ],
    },
    {
        "category": "Advanced Shapes",
        "items": [
            {"label": "Torus / Ring", "prompt": "a torus with an overall diameter of 60mm and a tube thickness of 10mm"},
            {"label": "Hex Prism", "prompt": "a hexagonal prism 30mm across and 20mm tall"},
            {"label": "Pyramid", "prompt": "a pyramid with a 40mm square base and 30mm height"},
            {"label": "5-Point Star", "prompt": "a 5 pointed star, 40mm outer diameter, 16mm inner diameter, 10mm thick"},
        ],
    },
    {
        "category": "Functional Parts",
        "items": [
            {
                "label": "Bolt-Circle Flange",
                "prompt": "a cylinder 60mm diameter and 10mm tall with 6 bolt holes of 4mm diameter "
                          "arranged in a circle of 20mm radius on the top face",
            },
            {
                "label": "Perforated Plate",
                "prompt": "a box 80mm wide, 80mm deep, 10mm tall with a 3x3 grid of 5mm square holes "
                          "spaced 20mm apart on the top face",
            },
            {
                "label": "Hollow Enclosure",
                "prompt": "a box 60mm wide, 60mm deep, 40mm tall, hollowed out with a 3mm wall thickness "
                          "and the top face open",
            },
            {
                "label": "Nameplate",
                "prompt": "a box 100mm wide, 100mm deep, 20mm tall, engrave the name 'CHRISTOPHER' "
                          "3mm deep into the top face, with 2mm filleted edges",
            },
            {
                "label": "Washer",
                "prompt": "a hollow cylinder outer diameter 20mm inner diameter 8mm height 2mm",
            },
            {
                "label": "Mounting Boss",
                "prompt": "a cylinder 25mm diameter and 15mm tall with a 4.5mm circular hole "
                          "through the center on the top face, fillet edges 1mm",
            },
        ],
    },
    {
        "category": "Engineering",
        "items": [
            {
                "label": "Beam Blank 40×60",
                "prompt": "a box 40mm wide, 60mm deep, and 500mm tall",
            },
            {
                "label": "Round Bar Ø30",
                "prompt": "a cylinder 30mm diameter and 400mm tall",
            },
            {
                "label": "Lid with Logo",
                "prompt": "a box 80mm wide 80mm deep 5mm tall, emboss 'CAD FORGE' 1mm high "
                          "on the top face, fillet edges 1mm",
            },
        ],
    },
    {
        "category": "Everyday objects",
        "items": [
            {"label": "Water Bottle", "prompt": "a water bottle 220mm tall"},
            {"label": "Coffee Mug", "prompt": "a coffee mug 90mm tall with 3mm walls"},
            {"label": "Chair", "prompt": "a simple wooden chair"},
            {"label": "Dining Table", "prompt": "a dining table 1200mm wide"},
            {"label": "Bookshelf", "prompt": "a bookshelf with 4 shelves"},
            {"label": "Phone Stand", "prompt": "a phone stand"},
            {"label": "Desk Lamp", "prompt": "a desk lamp"},
            {"label": "Bowl", "prompt": "a mixing bowl 160mm diameter"},
            {"label": "Coaster", "prompt": "a coaster 90mm diameter and 5mm thick"},
            {"label": "Plate", "prompt": "a dinner plate 220mm diameter"},
        ],
    },
]


def list_templates() -> list:
    return TEMPLATES
