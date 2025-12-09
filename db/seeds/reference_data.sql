BEGIN;

UPDATE regions SET name = 'Bay Area' WHERE slug = 'bay-area';
INSERT INTO regions (name, slug)
SELECT 'Bay Area', 'bay-area'
WHERE NOT EXISTS (
    SELECT 1 FROM regions WHERE slug = 'bay-area'
);

UPDATE regions SET name = 'Sacramento' WHERE slug = 'sacramento';
INSERT INTO regions (name, slug)
SELECT 'Sacramento', 'sacramento'
WHERE NOT EXISTS (
    SELECT 1 FROM regions WHERE slug = 'sacramento'
);

DO $$
DECLARE
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT *
        FROM (VALUES
            ('AAAT', 'Active Adult Attached', 'Active Adult'),
            ('AASF', 'Active Adult Single-Family Detached', 'Active Adult'),
            ('ATMU', 'Attached Move-up', 'Attached'),
            ('ATST', 'Attached Starter', 'Attached'),
            ('ATT', 'Single Family Attached', 'Attached'),
            ('COHT', 'Condo / Hotel', 'Attached'),
            ('CONV', 'Conversion', 'Attached'),
            ('DTMU', 'Detached Move-up', 'Detached'),
            ('DTST', 'Detached Starter', 'Detached'),
            ('HIGH', 'High Rise', 'Attached'),
            ('LOFT', 'Loft', 'Attached'),
            ('MIDR', 'Mid-Rise', 'Attached'),
            ('RWHS', 'Row Houses', 'Attached'),
            ('SFD', 'Single Family Detached', 'Detached')
        ) AS t(code, description, category)
    LOOP
        UPDATE product_types
        SET description = rec.description,
            category = rec.category
        WHERE product_type_code = rec.code;

        IF NOT FOUND THEN
            INSERT INTO product_types (product_type_code, description, category)
            VALUES (rec.code, rec.description, rec.category);
        END IF;
    END LOOP;
END $$;

DO $$
DECLARE
    rec RECORD;
    sacramento_id INTEGER;
    bay_area_id INTEGER;
BEGIN
    SELECT region_id INTO sacramento_id FROM regions WHERE slug = 'sacramento';
    SELECT region_id INTO bay_area_id FROM regions WHERE slug = 'bay-area';

    FOR rec IN
        SELECT *
        FROM (VALUES
            (sacramento_id, 'Placer / Nevada | Placer County', 'Placer / Nevada (Placer County)', 10),
            (sacramento_id, 'Placer / Nevada | Nevada County', 'Placer / Nevada (Nevada County)', 11),
            (sacramento_id, 'Yolo | Yolo County', 'Yolo County', 20),
            (sacramento_id, 'Northern Counties | Butte County', 'Northern Counties (Butte)', 30),
            (sacramento_id, 'Northern Counties | Yuba County', 'Northern Counties (Yuba)', 31),
            (sacramento_id, 'Northern Counties | Sutter County', 'Northern Counties (Sutter)', 32),
            (sacramento_id, 'Northern Counties | Shasta County', 'Northern Counties (Shasta)', 33),
            (bay_area_id, 'Alameda County | Alameda County', 'Alameda County (Core)', 10),
            (bay_area_id, 'Alameda County | Amador Valley', 'Alameda County (Amador Valley)', 11)
        ) AS t(region_id, name, display_name, display_order)
    LOOP
        IF rec.region_id IS NULL THEN
            CONTINUE;
        END IF;

        UPDATE county_groups
        SET display_name = rec.display_name,
            display_order = rec.display_order
        WHERE region_id = rec.region_id
          AND name = rec.name;

        IF NOT FOUND THEN
            INSERT INTO county_groups (region_id, name, display_name, display_order)
            VALUES (rec.region_id, rec.name, rec.display_name, rec.display_order);
        END IF;
    END LOOP;
END $$;

DO $$
DECLARE
    rec RECORD;
    sacramento_id INTEGER;
    bay_area_id INTEGER;
    placer_id INTEGER;
    nevada_id INTEGER;
    yolo_id INTEGER;
    butte_id INTEGER;
    yuba_id INTEGER;
    sutter_id INTEGER;
    shasta_id INTEGER;
    alameda_core_id INTEGER;
    amador_valley_id INTEGER;
BEGIN
    SELECT region_id INTO sacramento_id FROM regions WHERE slug = 'sacramento';
    SELECT region_id INTO bay_area_id FROM regions WHERE slug = 'bay-area';

    SELECT county_group_id INTO placer_id FROM county_groups
        WHERE name = 'Placer / Nevada | Placer County' AND region_id = sacramento_id;
    SELECT county_group_id INTO nevada_id FROM county_groups
        WHERE name = 'Placer / Nevada | Nevada County' AND region_id = sacramento_id;
    SELECT county_group_id INTO yolo_id FROM county_groups
        WHERE name = 'Yolo | Yolo County' AND region_id = sacramento_id;
    SELECT county_group_id INTO butte_id FROM county_groups
        WHERE name = 'Northern Counties | Butte County' AND region_id = sacramento_id;
    SELECT county_group_id INTO yuba_id FROM county_groups
        WHERE name = 'Northern Counties | Yuba County' AND region_id = sacramento_id;
    SELECT county_group_id INTO sutter_id FROM county_groups
        WHERE name = 'Northern Counties | Sutter County' AND region_id = sacramento_id;
    SELECT county_group_id INTO shasta_id FROM county_groups
        WHERE name = 'Northern Counties | Shasta County' AND region_id = sacramento_id;
    SELECT county_group_id INTO alameda_core_id FROM county_groups
        WHERE name = 'Alameda County | Alameda County' AND region_id = bay_area_id;
    SELECT county_group_id INTO amador_valley_id FROM county_groups
        WHERE name = 'Alameda County | Amador Valley' AND region_id = bay_area_id;

    FOR rec IN
        SELECT *
        FROM (VALUES
            ('RV', 'Roseville', sacramento_id, placer_id),
            ('RK', 'Rocklin', sacramento_id, placer_id),
            ('GB', 'Granite Bay', sacramento_id, placer_id),
            ('LL', 'Lincoln', sacramento_id, placer_id),
            ('GV', 'Grass Valley', sacramento_id, nevada_id),
            ('WS', 'West Sacramento', sacramento_id, yolo_id),
            ('DV', 'Davis', sacramento_id, yolo_id),
            ('WL', 'Woodland', sacramento_id, yolo_id),
            ('WN', 'Winters', sacramento_id, yolo_id),
            ('CO', 'Chico', sacramento_id, butte_id),
            ('PLK', 'Plumas Lake', sacramento_id, yuba_id),
            ('YC', 'Yuba City', sacramento_id, sutter_id),
            ('RD', 'Redding', sacramento_id, shasta_id),
            ('CV', 'Castro Valley', bay_area_id, alameda_core_id),
            ('AL', 'Alameda', bay_area_id, alameda_core_id),
            ('DB', 'Dublin', bay_area_id, amador_valley_id),
            ('LV', 'Livermore', bay_area_id, amador_valley_id),
            ('LF', 'Lafayette', bay_area_id, alameda_core_id),
            ('MZ', 'Martinez', bay_area_id, alameda_core_id),
            ('WC', 'Walnut Creek', bay_area_id, alameda_core_id)
        ) AS t(code, name, region_id, county_group_id)
    LOOP
        IF rec.region_id IS NULL THEN
            CONTINUE;
        END IF;

        UPDATE city_codes
        SET name = rec.name,
            region_id = rec.region_id,
            county_group_id = rec.county_group_id
        WHERE city_code = rec.code;

        IF NOT FOUND THEN
            INSERT INTO city_codes (city_code, name, region_id, county_group_id)
            VALUES (rec.code, rec.name, rec.region_id, rec.county_group_id);
        END IF;
    END LOOP;
END $$;

COMMIT;
