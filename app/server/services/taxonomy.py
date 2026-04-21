from __future__ import annotations

from typing import Iterable


CANONICAL_CATEGORY_ORDER = ["Hardware", "Software", "Utilities", "Facilities", "Interiors"]
CANONICAL_CATEGORY_NAMES = set(CANONICAL_CATEGORY_ORDER)

LEGACY_CATEGORY_ALIASES = {
    "Software Licenses": ("Software", "Licenses"),
    "Cloud Subscriptions": ("Software", "Subscriptions"),
    "Interior": ("Interiors", None),
    "Electronics": ("Hardware", None),
}

CANONICAL_TAXONOMY = [
    {
        "name": "Hardware",
        "description": "Physical IT equipment and endpoint devices.",
        "asset_behavior": "instance_based",
        "subcategories": [
            {"name": "Laptops", "description": "Portable computers.", "attrs": ["RAM", "CPU", "Storage"]},
            {"name": "Desktops", "description": "Desktop workstations.", "attrs": ["RAM", "CPU", "Storage"]},
            {"name": "Monitors", "description": "Display devices.", "attrs": ["Resolution", "Ports"]},
        ],
    },
    {
        "name": "Software",
        "description": "Software licenses and subscriptions.",
        "asset_behavior": "license_based",
        "subcategories": [
            {"name": "Licenses", "description": "Per-user or perpetual software licenses.", "attrs": ["License Key", "Renewal Date"]},
            {"name": "Subscriptions", "description": "Recurring software subscriptions and SaaS plans.", "attrs": ["Plan", "Renewal Date"]},
        ],
    },
    {
        "name": "Utilities",
        "description": "Shared utilities and power support assets.",
        "asset_behavior": "instance_based",
        "subcategories": [
            {"name": "AC Units", "description": "Cooling systems.", "attrs": ["BTU", "Energy Rating", "Inverter"]},
            {"name": "Fans", "description": "Ventilation equipment.", "attrs": ["Wattage", "Sweep Size", "Speed Settings"]},
            {"name": "UPS Systems", "description": "Backup power systems.", "attrs": ["KVA", "Backup Time"]},
            {"name": "Generators", "description": "Standby generators.", "attrs": ["KVA", "Fuel Type"]},
        ],
    },
    {
        "name": "Facilities",
        "description": "Workspace and building facilities.",
        "asset_behavior": "instance_based",
        "subcategories": [
            {"name": "Cabins", "description": "Office cabins and enclosed workspaces.", "attrs": ["Area", "Capacity"]},
            {"name": "Meeting Rooms", "description": "Shared meeting spaces.", "attrs": ["Capacity", "Location"]},
            {"name": "Partitions", "description": "Space dividers and partitions.", "attrs": ["Material", "Height"]},
        ],
    },
    {
        "name": "Interiors",
        "description": "Furniture and interior fixtures.",
        "asset_behavior": "instance_based",
        "subcategories": [
            {"name": "Chairs", "description": "Office seating.", "attrs": ["Material", "Ergonomic"]},
            {"name": "Tables", "description": "Tables and desks.", "attrs": ["Dimensions", "Material"]},
            {"name": "Cabinets", "description": "Storage units and cabinets.", "attrs": ["Material", "Shelves"]},
        ],
    },
]


def is_visible_category_name(category_name: str | None) -> bool:
    canonical = canonical_category_name(category_name)
    return bool(canonical and canonical in CANONICAL_CATEGORY_NAMES)


def canonical_category_name(category_name: str | None) -> str | None:
    if not category_name:
        return None
    stripped = category_name.strip()
    if stripped in CANONICAL_CATEGORY_NAMES:
        return stripped
    return LEGACY_CATEGORY_ALIASES.get(stripped, (stripped, None))[0]


def canonical_subcategory_name(category_name: str | None, subcategory_name: str | None) -> str | None:
    if not subcategory_name:
        return None
    stripped = subcategory_name.strip()
    if not category_name:
        return stripped
    allowed = canonical_subcategory_names_for_category(category_name)
    if stripped in allowed:
        return stripped
    legacy = LEGACY_CATEGORY_ALIASES.get(category_name.strip())
    if legacy and legacy[1] and legacy[1] in allowed:
        return legacy[1]
    return None


def canonical_subcategory_names_for_category(category_name: str | None) -> set[str]:
    canonical = canonical_category_name(category_name)
    if not canonical:
        return set()
    for category in CANONICAL_TAXONOMY:
        if category["name"] == canonical:
            return {sub["name"] for sub in category["subcategories"]}
    return set()


def _get_category_by_name(db, Category, category_name: str):
    return db.query(Category).filter(Category.category_name == category_name).first()


def _get_subcategory_by_name(db, SubCategory, category_id: str, subcategory_name: str):
    return (
        db.query(SubCategory)
        .filter(SubCategory.category_id == category_id)
        .filter(SubCategory.sub_category_name == subcategory_name)
        .first()
    )


def _move_category_contents(db, *, Category, SubCategory, Asset, source_category, target_category, target_subcategory_name: str | None = None):
    if source_category.category_id == target_category.category_id:
        return

    target_subcategory = None
    if target_subcategory_name:
        target_subcategory = _get_subcategory_by_name(db, SubCategory, target_category.category_id, target_subcategory_name)

    source_subcategories = db.query(SubCategory).filter(SubCategory.category_id == source_category.category_id).all()
    for subcategory in source_subcategories:
        if target_subcategory_name and subcategory.sub_category_name == target_subcategory_name:
            continue
        subcategory.category_id = target_category.category_id

    assets = db.query(Asset).filter(Asset.category_id == source_category.category_id).all()
    for asset in assets:
        asset.category_id = target_category.category_id
        if target_subcategory and not asset.sub_category_id:
            asset.sub_category_id = target_subcategory.sub_category_id


def ensure_canonical_taxonomy(db) -> None:
    from app.server.schema.asset import Asset
    from app.server.schema.attribute import AssetAttribute
    from app.server.schema.category import Category, SubCategory

    categories_by_name = {
        row.category_name: row
        for row in db.query(Category).all()
    }

    # Merge legacy Electronics category into Hardware.
    electronics = categories_by_name.get("Electronics")
    hardware = categories_by_name.get("Hardware")
    if electronics and hardware:
        _move_category_contents(
            db,
            Category=Category,
            SubCategory=SubCategory,
            Asset=Asset,
            source_category=electronics,
            target_category=hardware,
        )

    # Normalize legacy names where there is a one-to-one mapping.
    interior = categories_by_name.get("Interior")
    interiors = categories_by_name.get("Interiors")
    if interior and not interiors:
        interior.category_name = "Interiors"
        interiors = interior
        categories_by_name["Interiors"] = interior
        categories_by_name.pop("Interior", None)
    elif interior and interiors:
        _move_category_contents(db, Category=Category, SubCategory=SubCategory, Asset=Asset, source_category=interior, target_category=interiors)

    software = categories_by_name.get("Software")
    if not software:
        legacy_software_source = categories_by_name.get("Software Licenses") or categories_by_name.get("Cloud Subscriptions")
        if legacy_software_source:
            legacy_software_source.category_name = "Software"
            software = legacy_software_source
            categories_by_name["Software"] = legacy_software_source
        else:
            software = Category(
                category_name="Software",
                description="Software licenses and subscriptions.",
                asset_behavior="license_based",
                organization_id=None,
            )
            db.add(software)
            db.flush()
            categories_by_name["Software"] = software

    facilities = categories_by_name.get("Facilities")
    if not facilities:
        facilities = Category(
            category_name="Facilities",
            description="Workspace and building facilities.",
            asset_behavior="instance_based",
            organization_id=None,
        )
        db.add(facilities)
        db.flush()
        categories_by_name["Facilities"] = facilities

    canonical_categories = {item["name"]: item for item in CANONICAL_TAXONOMY}

    for config in CANONICAL_TAXONOMY:
        category = categories_by_name.get(config["name"])
        if not category:
            category = Category(
                category_name=config["name"],
                description=config["description"],
                asset_behavior=config["asset_behavior"],
                organization_id=None,
            )
            db.add(category)
            db.flush()
            categories_by_name[config["name"]] = category
        else:
            category.description = config["description"]
            category.asset_behavior = config["asset_behavior"]

        for sub_config in config["subcategories"]:
            subcategory = _get_subcategory_by_name(db, SubCategory, category.category_id, sub_config["name"])
            if not subcategory:
                subcategory = SubCategory(
                    category_id=category.category_id,
                    sub_category_name=sub_config["name"],
                    description=sub_config["description"],
                    organization_id=None,
                )
                db.add(subcategory)
                db.flush()

            for attr_name in sub_config["attrs"]:
                existing_attr = (
                    db.query(AssetAttribute)
                    .filter(AssetAttribute.sub_category_id == subcategory.sub_category_id)
                    .filter(AssetAttribute.attribute_name == attr_name)
                    .first()
                )
                if not existing_attr:
                    db.add(
                        AssetAttribute(
                            sub_category_id=subcategory.sub_category_id,
                            attribute_name=attr_name,
                            data_type="String",
                            is_required=False,
                            organization_id=None,
                        )
                    )

    # Migrate software-related legacy categories to the canonical Software category.
    software = categories_by_name["Software"]
    software_subcategory_map = {
        "Software Licenses": _get_subcategory_by_name(db, SubCategory, software.category_id, "Licenses"),
        "Cloud Subscriptions": _get_subcategory_by_name(db, SubCategory, software.category_id, "Subscriptions"),
    }

    for legacy_name, target_subcategory in software_subcategory_map.items():
        source_category = categories_by_name.get(legacy_name)
        if not source_category:
            continue
        _move_category_contents(
            db,
            Category=Category,
            SubCategory=SubCategory,
            Asset=Asset,
            source_category=source_category,
            target_category=software,
            target_subcategory_name=target_subcategory.sub_category_name if target_subcategory else None,
        )

    # Move cabin-style facilities out of Interiors and into Facilities when they already exist.
    cabins = _get_subcategory_by_name(db, SubCategory, facilities.category_id, "Cabins")
    if not cabins:
        interiors_category = categories_by_name.get("Interiors")
        if interiors_category:
            source_cabins = _get_subcategory_by_name(db, SubCategory, interiors_category.category_id, "Cabins")
            if source_cabins:
                source_cabins.category_id = facilities.category_id
                for asset in db.query(Asset).filter(Asset.sub_category_id == source_cabins.sub_category_id).all():
                    asset.category_id = facilities.category_id


def visible_category_names(rows: Iterable[str]) -> list[str]:
    canonical_names = {
        canonical_category_name(name)
        for name in rows
        if is_visible_category_name(name)
    }
    names = [name for name in canonical_names if name]
    order_map = {name: index for index, name in enumerate(CANONICAL_CATEGORY_ORDER)}
    return sorted(names, key=lambda name: (order_map.get(name, 999), name.lower()))
