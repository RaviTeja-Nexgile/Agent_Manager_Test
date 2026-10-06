-- =============================================================================
-- CCFP IT Solution - Seed 0012: PCI field definitions for Phase-1 HDT (PCI-3)
-- =============================================================================
-- §19.2 (l.840): per-field required/optional flags for the configurable PCI
-- form. Seeds the Phase-1 Heavy-Duty Truck study (PHASE1-HDT) field definitions
-- for the single-valued sections. The required set is deliberately SMALL and
-- realistic (a few per section) so investigations can still be submitted in
-- tests; the orange/optional fields are marked is_optional=true.
--
-- field_code values MUST match the structured column keys created in migration
-- 0014 so submit-time validation can look them up directly in the stored
-- sections. study_id is resolved by subquery on the PHASE1-HDT study code.
-- Idempotent: ON CONFLICT (study_id, section_code, field_code) DO NOTHING.
-- =============================================================================

INSERT INTO pci_field_definitions
    (study_id, section_code, field_code, label, is_required, is_optional, display_order)
SELECT s.id, d.section_code, d.field_code, d.label, d.is_required, NOT d.is_required, d.display_order
FROM studies s
CROSS JOIN (VALUES
    -- CARRIER_POWER_UNIT (pci_carrier_power_unit columns) ---------------------
    ('CARRIER_POWER_UNIT', 'carrier_name_displayed', 'Carrier name displayed',     TRUE,  10),
    ('CARRIER_POWER_UNIT', 'vin',                    'VIN',                         TRUE,  20),
    ('CARRIER_POWER_UNIT', 'make',                   'Make',                        FALSE, 30),
    ('CARRIER_POWER_UNIT', 'model',                  'Model',                       FALSE, 40),
    ('CARRIER_POWER_UNIT', 'year',                   'Year',                        FALSE, 50),
    ('CARRIER_POWER_UNIT', 'gvwr',                   'GVWR',                        FALSE, 60),
    ('CARRIER_POWER_UNIT', 'fire',                   'Fire (yes/no)',               FALSE, 70),
    ('CARRIER_POWER_UNIT', 'license_plate',          'License plate',               FALSE, 80),

    -- DRIVER_LOAD (pci_driver_load columns) -----------------------------------
    ('DRIVER_LOAD', 'driver_name',          'Driver name',         TRUE,  10),
    ('DRIVER_LOAD', 'driver_present',       'Driver present',      FALSE, 20),
    ('DRIVER_LOAD', 'license_number',       'License number',      FALSE, 30),
    ('DRIVER_LOAD', 'license_state',        'License State',       FALSE, 40),
    ('DRIVER_LOAD', 'license_class',        'License class',       FALSE, 50),
    ('DRIVER_LOAD', 'cargo_loaded',         'Cargo loaded',        FALSE, 60),
    ('DRIVER_LOAD', 'load_securement',      'Load securement',     FALSE, 70),

    -- MEDICAL_CERTIFICATE (pci_medical_certificate columns) -------------------
    ('MEDICAL_CERTIFICATE', 'examination_date', 'Examination date', FALSE, 10),
    ('MEDICAL_CERTIFICATE', 'expiration_date',  'Expiration date',  FALSE, 20),
    ('MEDICAL_CERTIFICATE', 'lenses',           'Lenses',           FALSE, 30),
    ('MEDICAL_CERTIFICATE', 'hearing_aid',      'Hearing aid',      FALSE, 40),
    ('MEDICAL_CERTIFICATE', 'waiver',           'Waiver',           FALSE, 50),

    -- HOURS_OF_SERVICE (pci_hours_of_service columns) -------------------------
    ('HOURS_OF_SERVICE', 'driving_hours',        'Driving hours',         TRUE,  10),
    ('HOURS_OF_SERVICE', 'total_on_duty_hours',  'Total on-duty hours',   FALSE, 20),
    ('HOURS_OF_SERVICE', 'record_of_duty_status','Record of duty status', FALSE, 30),
    ('HOURS_OF_SERVICE', 'eld_present',          'ELD present',           FALSE, 40),
    ('HOURS_OF_SERVICE', 'co_driver',            'Co-driver',             FALSE, 50),
    ('HOURS_OF_SERVICE', 'years_experience',     'Years experience',      FALSE, 60),

    -- EXEMPTIONS (pci_exemptions columns) -------------------------------------
    ('EXEMPTIONS', 'exemption_14_hour',        '14-hour workday',        FALSE, 10),
    ('EXEMPTIONS', 'exemption_11_hour',        '11-hour driving period', FALSE, 20),
    ('EXEMPTIONS', 'exemption_60_70_hour',     '60/70-hour week',        FALSE, 30),
    ('EXEMPTIONS', 'exemption_34_hour_restart','34-hour restart',        FALSE, 40),
    ('EXEMPTIONS', 'docket_or_state_number',   'Docket or State number', FALSE, 50),

    -- VEHICLE_CONDITION (pci_vehicle_condition columns) -----------------------
    ('VEHICLE_CONDITION', 'compartment_condition', 'Driver''s compartment condition', FALSE, 10),
    ('VEHICLE_CONDITION', 'drivers_view',          'Driver''s view',                  FALSE, 20),
    ('VEHICLE_CONDITION', 'odometer',              'Odometer',                       FALSE, 30),
    ('VEHICLE_CONDITION', 'engine_manufacturer',   'Engine manufacturer',            FALSE, 40),
    ('VEHICLE_CONDITION', 'fuel_type',             'Fuel type',                      FALSE, 50),
    ('VEHICLE_CONDITION', 'steering_type',         'Steering type',                  FALSE, 60),
    ('VEHICLE_CONDITION', 'transmission_type',     'Transmission type',              FALSE, 70),

    -- BRAKE_SYSTEM (pci_brake_system columns) ---------------------------------
    ('BRAKE_SYSTEM', 'brake_type',             'Brake type',             TRUE,  10),
    ('BRAKE_SYSTEM', 'abs_type',               'ABS type',               FALSE, 20),
    ('BRAKE_SYSTEM', 'air_leaks',              'Air leaks',              FALSE, 30),
    ('BRAKE_SYSTEM', 'parking_brake',          'Parking brake',          FALSE, 40),
    ('BRAKE_SYSTEM', 'low_air_vacuum_warning', 'Low-air/vacuum warning', FALSE, 50)
) AS d(section_code, field_code, label, is_required, display_order)
WHERE s.code = 'PHASE1-HDT'
ON CONFLICT (study_id, section_code, field_code) DO NOTHING;
