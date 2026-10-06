import * as React from 'react';
import { Plus, Send, Trash2 } from 'lucide-react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useApi } from '@/lib/useApi';
import { sourceApi, studyApi } from '@/lib/endpoints';
import { ApiError } from '@/lib/api';
import type {
  AdditionalTowedUnitData,
  AxleData,
  HazmatData,
  InvestigationWrite,
  PciFieldDefinition,
  PostCrashInvestigation,
  SeatingPositionData,
  TireData,
  TrailerData,
} from '@/lib/types';

// ─────────────────────────────────────────────────────────────────────────────
// Declarative field schema. §19.2 (Appendix B) is large, so every section is
// described once as a list of {key, type, label} and both the editor render
// path and the structured-payload builder are driven off this single source.
// `type` maps a structured field to the right control + the right JSON coercion
// (bool->boolean, int/numeric->number, date->"YYYY-MM-DD", text->string).
// ─────────────────────────────────────────────────────────────────────────────

type FieldType = 'text' | 'textarea' | 'bool' | 'int' | 'numeric' | 'date';

interface FieldSpec {
  key: string;
  label: string;
  type: FieldType;
  /** Fixed option set for a constrained text field (rendered as a Select). */
  options?: { value: string; label: string }[];
}

interface SectionSpec {
  /** Matches a PciFieldDefinition.section_code and the structured key on the payload. */
  code: string;
  attr: keyof InvestigationWrite;
  title: string;
  fields: FieldSpec[];
}

const T = (key: string, label: string): FieldSpec => ({ key, label, type: 'text' });
const TA = (key: string, label: string): FieldSpec => ({ key, label, type: 'textarea' });
const B = (key: string, label: string): FieldSpec => ({ key, label, type: 'bool' });
const I = (key: string, label: string): FieldSpec => ({ key, label, type: 'int' });
const N = (key: string, label: string): FieldSpec => ({ key, label, type: 'numeric' });
const D = (key: string, label: string): FieldSpec => ({ key, label, type: 'date' });

// ── Single-valued §19.2 sections (one-to-one) ───────────────────────────────
const CARRIER_POWER_UNIT_FIELDS: FieldSpec[] = [
  B('work_zone', 'Work zone'),
  T('work_zone_type', 'Work zone type'),
  T('preclearance_bypass_serial', 'Preclearance / bypass serial'),
  B('fire', 'Fire'),
  B('fire_pre_crash', 'Fire pre-crash'),
  B('fire_post_crash', 'Fire post-crash'),
  T('carrier_name_displayed', 'Carrier name displayed'),
  B('us_dot_displayed', 'US DOT displayed'),
  T('nsc_number', 'NSC number'),
  T('motor_carrier_name', 'Motor carrier name'),
  T('motor_carrier_address', 'Motor carrier address'),
  T('motor_carrier_phone', 'Motor carrier phone'),
  T('owner_name', 'Owner name'),
  T('owner_address', 'Owner address'),
  B('lease_indicator', 'Leased'),
  I('year', 'Year'),
  T('make', 'Make'),
  T('model', 'Model'),
  T('company_unit_number', 'Company unit number'),
  D('manufacture_date', 'Manufacture date'),
  T('vin', 'VIN'),
  T('color', 'Color'),
  T('license_plate', 'License plate'),
  T('license_plate_state', 'License plate state'),
  N('registered_gross_weight', 'Registered gross weight'),
  N('gvwr', 'GVWR'),
  B('annual_inspection', 'Annual inspection'),
  I('axles_up', 'Axles up'),
  I('axles_down', 'Axles down'),
  TA('remarks', 'Remarks'),
];

const DRIVER_LOAD_FIELDS: FieldSpec[] = [
  T('driver_name', 'Driver name'),
  B('driver_present', 'Driver present'),
  T('driver_address', 'Driver address'),
  T('license_state', 'License state'),
  T('license_province', 'License province'),
  T('license_number', 'License number'),
  T('license_class', 'License class'),
  T('license_endorsements', 'License endorsements'),
  T('license_restrictions', 'License restrictions'),
  D('license_issue_date', 'License issue date'),
  D('license_expiration_date', 'License expiration date'),
  B('lenses_required', 'Lenses required'),
  B('lenses_worn', 'Lenses worn'),
  T('shipper', 'Shipper'),
  T('bill_of_lading', 'Bill of lading'),
  N('manifest_load_weight', 'Manifest load weight'),
  T('cargo_loaded', 'Cargo loaded'),
  T('cargo_destination', 'Cargo destination'),
  B('load_securement', 'Load securement'),
  B('securement_contributed', 'Securement contributed'),
  B('securement_proper_use', 'Securement proper use'),
  B('securement_exceeded_wll', 'Securement exceeded WLL'),
  T('securement_type', 'Securement type'),
  TA('remarks', 'Remarks'),
];

const MEDICAL_CERTIFICATE_FIELDS: FieldSpec[] = [
  D('examination_date', 'Examination date'),
  D('expiration_date', 'Expiration date'),
  B('lenses', 'Lenses'),
  B('hearing_aid', 'Hearing aid'),
  B('waiver', 'Waiver'),
  B('medic_alert', 'Medic alert'),
  T('cert_state', 'Certificate state'),
  T('cert_province', 'Certificate province'),
  TA('remarks', 'Remarks'),
];

const HOURS_OF_SERVICE_FIELDS: FieldSpec[] = [
  N('on_duty_not_driving_hours', 'On-duty (not driving) hours'),
  N('driving_hours', 'Driving hours'),
  N('total_on_duty_hours', 'Total on-duty hours'),
  N('miles_driven', 'Miles driven'),
  N('kilometers_driven', 'Kilometers driven'),
  B('record_of_duty_status', 'Record of duty status'),
  B('timecard', 'Timecard'),
  T('violations', 'Violations'),
  B('onboard_computer_eld', 'Onboard computer / ELD'),
  B('eld_present', 'ELD present'),
  B('co_driver', 'Co-driver'),
  B('last_8_days_present', 'Last 8 days present'),
  B('approved_eld', 'Approved ELD'),
  T('driver_history', 'Driver history'),
  T('road_familiarity', 'Road familiarity'),
  N('years_experience', 'Years experience'),
  I('previous_cmv_crashes', 'Previous CMV crashes'),
  T('purpose_of_trip', 'Purpose of trip'),
  T('trip_destination', 'Trip destination'),
  TA('driver_condition_remarks', 'Driver condition remarks'),
];

const EXEMPTIONS_FIELDS: FieldSpec[] = [
  B('exemption_14_hour', '14-hour exemption'),
  B('exemption_11_hour', '11-hour exemption'),
  B('exemption_split_sleeper', 'Split sleeper exemption'),
  B('exemption_60_70_hour', '60/70-hour exemption'),
  B('exemption_34_hour_restart', '34-hour restart exemption'),
  B('exemption_federal', 'Federal exemption'),
  B('exemption_state', 'State exemption'),
  B('exemption_oilfield', 'Oilfield exemption'),
  B('exemption_agricultural', 'Agricultural exemption'),
  B('exemption_150_air_mile', '150 air-mile exemption'),
  B('exemption_temporary', 'Temporary exemption'),
  T('docket_or_state_number', 'Docket / state number'),
  B('emergency_declaration', 'Emergency declaration'),
  T('emergency_jurisdiction', 'Emergency jurisdiction'),
  T('emergency_federal_number', 'Emergency federal number'),
  T('emergency_state_number', 'Emergency state number'),
  T('service_center', 'Service center'),
  TA('other_description', 'Other description'),
];

const VEHICLE_CONDITION_FIELDS: FieldSpec[] = [
  T('compartment_condition', 'Compartment condition'),
  T('drivers_view', "Driver's view"),
  T('wipers', 'Wipers'),
  T('wiper_switch_position', 'Wiper switch position'),
  T('heater_defroster', 'Heater / defroster'),
  T('mirrors', 'Mirrors'),
  B('rearward_camera', 'Rearward camera'),
  B('fender_mirrors', 'Fender mirrors'),
  N('odometer', 'Odometer'),
  N('engine_hours', 'Engine hours'),
  T('engine_manufacturer', 'Engine manufacturer'),
  T('fuel_type', 'Fuel type'),
  T('ecm_serial', 'ECM serial'),
  T('adas', 'ADAS'),
  T('steering_type', 'Steering type'),
  N('steering_wheel_diameter', 'Steering wheel diameter'),
  T('steering_lash', 'Steering lash'),
  B('steering_checked_running', 'Steering checked running'),
  T('transmission_type', 'Transmission type'),
  T('transmission_model', 'Transmission model'),
  T('transmission_serial', 'Transmission serial'),
  T('transmission_gear_position', 'Transmission gear position'),
  I('transmission_forward_gears', 'Transmission forward gears'),
  T('drive_line_notes', 'Drive line notes'),
  T('drive_axle_ratio', 'Drive axle ratio'),
  B('radio', 'Radio'),
  B('cb', 'CB'),
  B('dash_camera', 'Dash camera'),
  B('audio_technology', 'Audio technology'),
  B('headphones', 'Headphones'),
  B('bluetooth', 'Bluetooth'),
  TA('remarks', 'Remarks'),
];

const BRAKE_SYSTEM_FIELDS: FieldSpec[] = [
  T('brake_type', 'Brake type'),
  T('abs_type', 'ABS type'),
  T('engine_brake_type', 'Engine brake type'),
  T('engine_brake_position', 'Engine brake position'),
  B('air_leaks', 'Air leaks'),
  B('application_loss', 'Application loss'),
  B('low_air_vacuum_warning', 'Low air / vacuum warning'),
  N('low_air_vacuum_warning_psi', 'Low air / vacuum warning PSI'),
  B('hydraulic_master_cylinder_secure', 'Hydraulic master cylinder secure'),
  T('hydraulic_fluid_level', 'Hydraulic fluid level'),
  B('hydraulic_fluid_seepage', 'Hydraulic fluid seepage'),
  T('hydraulic_line_condition', 'Hydraulic line condition'),
  T('electric_controller_mfr', 'Electric controller mfr'),
  T('electric_gain_setting', 'Electric gain setting'),
  B('electric_breakaway_device', 'Electric breakaway device'),
  T('electric_battery_wiring', 'Electric battery wiring'),
  B('surge_breakaway_device', 'Surge breakaway device'),
  B('surge_fluid_leak', 'Surge fluid leak'),
  B('power_assist', 'Power assist'),
  B('parking_brake', 'Parking brake'),
  T('wheel_end_weight_note', 'Wheel-end weight note'),
  TA('remarks', 'Remarks'),
];

const SINGLE_SECTIONS: SectionSpec[] = [
  { code: 'CARRIER_POWER_UNIT', attr: 'carrier_power_unit', title: 'Carrier & power unit', fields: CARRIER_POWER_UNIT_FIELDS },
  { code: 'DRIVER_LOAD', attr: 'driver_load', title: 'Driver & load', fields: DRIVER_LOAD_FIELDS },
  { code: 'MEDICAL_CERTIFICATE', attr: 'medical_certificate', title: 'Medical certificate', fields: MEDICAL_CERTIFICATE_FIELDS },
  { code: 'HOURS_OF_SERVICE', attr: 'hours_of_service', title: 'Hours of service', fields: HOURS_OF_SERVICE_FIELDS },
  { code: 'EXEMPTIONS', attr: 'exemptions', title: 'Exemptions', fields: EXEMPTIONS_FIELDS },
  { code: 'VEHICLE_CONDITION', attr: 'vehicle_condition', title: 'Vehicle condition', fields: VEHICLE_CONDITION_FIELDS },
  { code: 'BRAKE_SYSTEM', attr: 'brake_system', title: 'Brake system', fields: BRAKE_SYSTEM_FIELDS },
];

// ── Repeating §19.2 structures (one-to-many, replace-on-write) ───────────────
const SEAT_POSITION_OPTIONS = [
  { value: 'DRIVER', label: 'Driver' },
  { value: 'PASSENGER_1', label: 'Passenger 1' },
  { value: 'PASSENGER_2', label: 'Passenger 2' },
  { value: 'SLEEPER_BERTH', label: 'Sleeper berth' },
];
const SIDE_OPTIONS = [
  { value: 'LEFT', label: 'Left' },
  { value: 'RIGHT', label: 'Right' },
];
const INNER_OUTER_OPTIONS = [
  { value: 'INSIDE', label: 'Inside' },
  { value: 'OUTSIDE', label: 'Outside' },
];

const SEATING_FIELDS: FieldSpec[] = [
  { key: 'position', label: 'Position', type: 'text', options: SEAT_POSITION_OPTIONS },
  B('seat_belt_equipped', 'Seat belt equipped'),
  B('seat_belt_used', 'Seat belt used'),
  T('seat_belt_condition', 'Seat belt condition'),
  B('airbag_equipped', 'Airbag equipped'),
  B('airbag_deployed', 'Airbag deployed'),
  TA('remarks', 'Remarks'),
];

const AXLE_FIELDS: FieldSpec[] = [
  I('axle_index', 'Axle index'),
  B('abs', 'ABS'),
  T('slack_adjuster_type', 'Slack adjuster type'),
  N('slack_adjuster_length', 'Slack adjuster length'),
  N('push_rod_stroke_available', 'Push rod stroke available'),
  N('push_rod_stroke_applied', 'Push rod stroke applied'),
  T('air_pressure', 'Air pressure'),
  T('chamber_type', 'Chamber type'),
  T('drum_rotor', 'Drum / rotor'),
  T('brake_friction_code', 'Brake friction code'),
  N('rolling_radius', 'Rolling radius'),
  N('wheel_end_weight', 'Wheel-end weight'),
  N('total_end_weight', 'Total end weight'),
  TA('remarks', 'Remarks'),
];

const TIRE_FIELDS: FieldSpec[] = [
  I('axle_index', 'Axle index'),
  { key: 'side', label: 'Side', type: 'text', options: SIDE_OPTIONS },
  { key: 'inner_outer', label: 'Inner / outer', type: 'text', options: INNER_OUTER_OPTIONS },
  T('size', 'Size'),
  T('make', 'Make'),
  T('model_design', 'Model / design'),
  T('tin_dot', 'TIN / DOT'),
  N('rated_psi', 'Rated PSI'),
  N('rated_weight', 'Rated weight'),
  N('inspection_psi', 'Inspection PSI'),
  T('retread_tin_dot', 'Retread TIN / DOT'),
  B('repair', 'Repair'),
  T('repair_location', 'Repair location'),
  T('speed_rating', 'Speed rating'),
  N('tread_depth', 'Tread depth'),
  TA('wheel_hub_remarks', 'Wheel / hub remarks'),
];

const TRAILER_FIELDS: FieldSpec[] = [
  I('trailer_index', 'Trailer index'),
  T('owner_name', 'Owner name'),
  T('owner_address', 'Owner address'),
  T('trailer_type', 'Trailer type'),
  B('intermodal_indicator', 'Intermodal'),
  T('unit_number', 'Unit number'),
  I('year', 'Year'),
  T('make', 'Make'),
  T('model', 'Model'),
  T('vin', 'VIN'),
  T('color', 'Color'),
  T('license_plate', 'License plate'),
  D('expiration', 'Expiration'),
  N('registered_gross_weight', 'Registered gross weight'),
  N('gvwr', 'GVWR'),
  N('axle_weight_rating', 'Axle weight rating'),
  B('annual_inspection', 'Annual inspection'),
  I('axles_up', 'Axles up'),
  I('axles_down', 'Axles down'),
  B('converter_dolly', 'Converter dolly'),
  T('converter_dolly_details', 'Converter dolly details'),
  TA('remarks', 'Remarks'),
];

// ── Optional conditional §19.2 sections (gated by presence flags) ────────────
const HAZMAT_FIELDS: FieldSpec[] = [
  T('unit_scope', 'Unit scope (e.g. TRUCK, TRAILER_1)'),
  B('hazmat_present', 'Hazmat present'),
  T('hazmat_type', 'Hazmat type'),
  T('placards', 'Placards'),
  B('spill', 'Spill'),
  B('leak', 'Leak'),
  TA('remarks', 'Remarks'),
];

const TOWED_FIELDS: FieldSpec[] = [
  I('towed_index', 'Towed index'),
  T('owner_name', 'Owner name'),
  T('owner_address', 'Owner address'),
  T('unit_type', 'Unit type'),
  T('unit_number', 'Unit number'),
  T('vin', 'VIN'),
  T('front_clearance', 'Front clearance'),
  T('rear_clearance', 'Rear clearance'),
  T('side_marker_left', 'Side marker left'),
  T('side_marker_right', 'Side marker right'),
  T('turn_signals', 'Turn signals'),
  T('stop_lamps', 'Stop lamps'),
  T('id_lamps', 'ID lamps'),
  T('tail_lamps', 'Tail lamps'),
  T('reflectors', 'Reflectors'),
  T('conspicuity_tape', 'Conspicuity tape'),
  N('distance_from_rear', 'Distance from rear'),
  N('rear_protection_from_rear', 'Rear protection from rear'),
  N('rear_protection_from_ground', 'Rear protection from ground'),
  N('rear_protection_from_side', 'Rear protection from side'),
  N('rear_protection_width', 'Rear protection width'),
  TA('remarks', 'Remarks'),
];

// ─────────────────────────────────────────────────────────────────────────────
// Form value modelling. Every field value is held as a string in form state for
// uniform control binding ('' = empty; checkboxes use 'true'/'false'); the
// payload builder coerces back to the typed JSON the API expects on save.
// ─────────────────────────────────────────────────────────────────────────────

type Row = Record<string, string>;

function emptyRow(fields: FieldSpec[]): Row {
  const r: Row = {};
  for (const f of fields) r[f.key] = '';
  return r;
}

/** Hydrate a form row from an API section/array-item object (any null -> ''). */
function rowFrom(obj: Record<string, unknown> | null | undefined, fields: FieldSpec[]): Row {
  const r = emptyRow(fields);
  if (!obj) return r;
  for (const f of fields) {
    const v = obj[f.key];
    if (v === null || v === undefined) continue;
    r[f.key] = f.type === 'bool' ? (v ? 'true' : 'false') : String(v);
  }
  return r;
}

/** Coerce a single string form value back to its typed JSON value (or null). */
function coerce(type: FieldType, raw: string): unknown {
  const v = raw.trim();
  if (type === 'bool') return raw === 'true' ? true : raw === 'false' ? false : null;
  if (v === '') return null;
  if (type === 'int') {
    const n = parseInt(v, 10);
    return Number.isNaN(n) ? null : n;
  }
  if (type === 'numeric') {
    const n = Number(v);
    return Number.isNaN(n) ? null : n;
  }
  return v; // text / textarea / date are sent as strings
}

/** Build the typed object payload for a section/array item from its form row. */
function payloadFrom(row: Row, fields: FieldSpec[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const f of fields) out[f.key] = coerce(f.type, row[f.key] ?? '');
  return out;
}

/** True when at least one field in the row carries a value (so we can skip empty single sections). */
function rowHasValue(row: Row, fields: FieldSpec[]): boolean {
  return fields.some((f) => {
    const v = row[f.key] ?? '';
    return f.type === 'bool' ? v === 'true' || v === 'false' : v.trim() !== '';
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Field controls
// ─────────────────────────────────────────────────────────────────────────────

interface FieldProps {
  spec: FieldSpec;
  value: string;
  onChange: (v: string) => void;
  required: boolean;
  readOnly: boolean;
}

function Field({ spec, value, onChange, required, readOnly }: FieldProps) {
  const id = React.useId();
  const label = (
    <Label htmlFor={id}>
      {spec.label}
      {required ? <span className="ml-0.5 text-destructive" aria-hidden> *</span> : null}
    </Label>
  );

  if (spec.type === 'bool') {
    return (
      <div className="flex items-center gap-2 self-end pb-2">
        <Checkbox
          id={id}
          checked={value === 'true'}
          disabled={readOnly}
          onChange={(e) => onChange(e.target.checked ? 'true' : 'false')}
        />
        {label}
      </div>
    );
  }

  let control: React.ReactNode;
  if (spec.options) {
    control = (
      <Select id={id} value={value} disabled={readOnly} onChange={(e) => onChange(e.target.value)}>
        <option value="">—</option>
        {spec.options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </Select>
    );
  } else if (spec.type === 'textarea') {
    control = <Textarea id={id} value={value} disabled={readOnly} onChange={(e) => onChange(e.target.value)} />;
  } else {
    const inputType = spec.type === 'date' ? 'date' : spec.type === 'int' || spec.type === 'numeric' ? 'number' : 'text';
    const step = spec.type === 'numeric' ? 'any' : undefined;
    control = (
      <Input
        id={id}
        type={inputType}
        step={step}
        value={value}
        disabled={readOnly}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  return (
    <div className={`space-y-1.5 ${spec.type === 'textarea' ? 'sm:col-span-2' : ''}`}>
      {label}
      {control}
    </div>
  );
}

/** A single-valued section's grid of fields. */
function SectionGrid({
  fields,
  row,
  setField,
  required,
  readOnly,
}: {
  fields: FieldSpec[];
  row: Row;
  setField: (key: string, v: string) => void;
  required: Set<string>;
  readOnly: boolean;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {fields.map((f) => (
        <Field
          key={f.key}
          spec={f}
          value={row[f.key] ?? ''}
          onChange={(v) => setField(f.key, v)}
          required={required.has(f.key)}
          readOnly={readOnly}
        />
      ))}
    </div>
  );
}

/** A repeating structure: add/remove rows, each rendered as a field grid. */
function RepeatingSection({
  label,
  fields,
  rows,
  setRows,
  readOnly,
}: {
  label: string;
  fields: FieldSpec[];
  rows: Row[];
  setRows: React.Dispatch<React.SetStateAction<Row[]>>;
  readOnly: boolean;
}) {
  function addRow() {
    setRows((prev) => {
      const next = emptyRow(fields);
      // Auto-increment the index column when present (axle_index / trailer_index / towed_index).
      const idxKey = fields.find((f) => f.key.endsWith('_index'))?.key;
      if (idxKey) next[idxKey] = String(prev.length + 1);
      return [...prev, next];
    });
  }
  function removeRow(i: number) {
    setRows((prev) => prev.filter((_, idx) => idx !== i));
  }
  function setField(i: number, key: string, v: string) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [key]: v } : r)));
  }

  return (
    <div className="space-y-3">
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No {label.toLowerCase()} rows.</p>
      ) : (
        rows.map((row, i) => (
          <div key={i} className="space-y-3 rounded-lg border bg-muted/20 p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {label} {i + 1}
              </span>
              {!readOnly ? (
                <Button variant="ghost" size="icon-sm" aria-label={`Remove ${label} ${i + 1}`} onClick={() => removeRow(i)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              ) : null}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {fields.map((f) => (
                <Field
                  key={f.key}
                  spec={f}
                  value={row[f.key] ?? ''}
                  onChange={(v) => setField(i, f.key, v)}
                  required={false}
                  readOnly={readOnly}
                />
              ))}
            </div>
          </div>
        ))
      )}
      {!readOnly ? (
        <Button variant="outline" size="xs" onClick={addRow}>
          <Plus className="h-3.5 w-3.5" /> Add {label.toLowerCase()}
        </Button>
      ) : null}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ELD summary (PCI-7). Editable summary fields on each linked ELD file.
// ─────────────────────────────────────────────────────────────────────────────

const DUTY_STATUS_OPTIONS = [
  { value: 'OFF_DUTY', label: 'Off duty' },
  { value: 'SLEEPER_BERTH', label: 'Sleeper berth' },
  { value: 'DRIVING', label: 'Driving' },
  { value: 'ON_DUTY_NOT_DRIVING', label: 'On duty (not driving)' },
];

/** Trim an ISO datetime to the `datetime-local` control format (YYYY-MM-DDTHH:mm). */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function EldSummarySection({ crashId, readOnly }: { crashId: string; readOnly: boolean }) {
  const { data: files, loading, reload } = useApi(() => sourceApi.eldFiles(crashId).catch(() => []), [crashId]);

  if (loading) return <Skeleton className="h-20 w-full" />;
  if (!files || files.length === 0) {
    return <p className="text-sm text-muted-foreground">No ELD files linked to this crash. Upload one from the ELD / eRODS tab first.</p>;
  }
  return (
    <div className="space-y-4">
      {files.map((f) => (
        <EldSummaryRow key={f.id} crashId={crashId} fileId={f.id} fileName={f.file_name}
          initial={{
            eld_downloaded: f.eld_downloaded ?? null,
            last_entry_at: toLocalInput(f.last_entry_at),
            last_duty_status: f.last_duty_status ?? '',
            last_stop_arrived_at: toLocalInput(f.last_stop_arrived_at),
            last_stop_departed_at: toLocalInput(f.last_stop_departed_at),
          }}
          readOnly={readOnly}
          onSaved={reload}
        />
      ))}
    </div>
  );
}

interface EldSummaryState {
  eld_downloaded: boolean | null;
  last_entry_at: string;
  last_duty_status: string;
  last_stop_arrived_at: string;
  last_stop_departed_at: string;
}

function EldSummaryRow({
  crashId,
  fileId,
  fileName,
  initial,
  readOnly,
  onSaved,
}: {
  crashId: string;
  fileId: string;
  fileName: string;
  initial: EldSummaryState;
  readOnly: boolean;
  onSaved: () => void;
}) {
  const [s, setS] = React.useState<EldSummaryState>(initial);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState(false);

  // `datetime-local` -> ISO (append seconds + Z); '' -> null.
  const iso = (local: string): string | null => (local ? new Date(local).toISOString() : null);

  async function save() {
    setBusy(true); setError(null); setSaved(false);
    try {
      await sourceApi.updateEldFile(crashId, fileId, {
        eld_downloaded: s.eld_downloaded,
        last_entry_at: iso(s.last_entry_at),
        last_duty_status: s.last_duty_status || null,
        last_stop_arrived_at: iso(s.last_stop_arrived_at),
        last_stop_departed_at: iso(s.last_stop_departed_at),
      });
      setSaved(true);
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
      <div className="text-sm font-medium">{fileName}</div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div className="flex items-center gap-2 self-end pb-2">
          <Checkbox
            checked={s.eld_downloaded === true}
            disabled={readOnly}
            onChange={(e) => setS({ ...s, eld_downloaded: e.target.checked })}
          />
          <Label>ELD downloaded</Label>
        </div>
        <div className="space-y-1.5">
          <Label>Last entry at</Label>
          <Input type="datetime-local" value={s.last_entry_at} disabled={readOnly}
            onChange={(e) => setS({ ...s, last_entry_at: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label>Last duty status</Label>
          <Select value={s.last_duty_status} disabled={readOnly}
            onChange={(e) => setS({ ...s, last_duty_status: e.target.value })}>
            <option value="">—</option>
            {DUTY_STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>Last stop arrived at</Label>
          <Input type="datetime-local" value={s.last_stop_arrived_at} disabled={readOnly}
            onChange={(e) => setS({ ...s, last_stop_arrived_at: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label>Last stop departed at</Label>
          <Input type="datetime-local" value={s.last_stop_departed_at} disabled={readOnly}
            onChange={(e) => setS({ ...s, last_stop_departed_at: e.target.value })} />
        </div>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {!readOnly ? (
        <div className="flex items-center gap-3">
          <Button size="xs" variant="outline" onClick={save} disabled={busy}>Save ELD summary</Button>
          {saved ? <span className="text-xs text-emerald-600">Saved</span> : null}
        </div>
      ) : null}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Editor
// ─────────────────────────────────────────────────────────────────────────────

const SECTION_TABS: { value: string; label: string }[] = [
  ...SINGLE_SECTIONS.map((s) => ({ value: s.code, label: s.title })),
  { value: 'SEATING', label: 'Seating positions' },
  { value: 'AXLES', label: 'Axles' },
  { value: 'TIRES', label: 'Tires' },
  { value: 'TRAILERS', label: 'Trailers' },
  { value: 'CONDITIONAL', label: 'Hazmat & towed units' },
  { value: 'ELD', label: 'ELD summary' },
];

export interface InvestigationFormProps {
  crashId: string;
  studyId: string;
  record: PostCrashInvestigation;
  canIngest: boolean;
  onClose: () => void;
  /** Called after a successful save/submit so the parent list can refresh. */
  onSaved: () => void;
}

export function InvestigationForm({ crashId, studyId, record, canIngest, onClose, onSaved }: InvestigationFormProps) {
  const readOnly = !canIngest;

  // Per-field required markers (PCI-3): section_code -> set of required field_codes.
  const { data: defs } = useApi(
    () => studyApi.pciFieldDefinitions(studyId).catch(() => [] as PciFieldDefinition[]),
    [studyId],
  );
  const requiredBySection = React.useMemo(() => {
    const map: Record<string, Set<string>> = {};
    for (const d of defs ?? []) {
      if (!d.is_required) continue;
      (map[d.section_code] ??= new Set()).add(d.field_code);
    }
    return map;
  }, [defs]);

  // Header fields owned by the parent investigation row.
  const [header, setHeader] = React.useState({
    case_number: record.case_number ?? '',
    inspection_number: record.inspection_number ?? '',
    officer_name: record.officer_name ?? '',
    officer_id: record.officer_id ?? '',
    post_crash_date: record.post_crash_date ?? '',
  });

  // Single-valued section rows keyed by section code.
  const [single, setSingle] = React.useState<Record<string, Row>>(() => {
    const init: Record<string, Row> = {};
    for (const s of SINGLE_SECTIONS) {
      init[s.code] = rowFrom(record[s.attr] as Record<string, unknown> | null, s.fields);
    }
    return init;
  });

  // Repeating structures.
  const [seating, setSeating] = React.useState<Row[]>(() => (record.seating_positions ?? []).map((r) => rowFrom(r, SEATING_FIELDS)));
  const [axles, setAxles] = React.useState<Row[]>(() => (record.axles ?? []).map((r) => rowFrom(r, AXLE_FIELDS)));
  const [tires, setTires] = React.useState<Row[]>(() => (record.tires ?? []).map((r) => rowFrom(r, TIRE_FIELDS)));
  const [trailers, setTrailers] = React.useState<Row[]>(() => (record.trailers ?? []).map((r) => rowFrom(r, TRAILER_FIELDS)));

  // Conditional sections + presence flags.
  const [hasHazmat, setHasHazmat] = React.useState(record.has_hazmat ?? false);
  const [hasTowed, setHasTowed] = React.useState(record.has_additional_towed_units ?? false);
  const [hazmat, setHazmat] = React.useState<Row[]>(() => (record.hazmat ?? []).map((r) => rowFrom(r, HAZMAT_FIELDS)));
  const [towed, setTowed] = React.useState<Row[]>(() => (record.additional_towed_units ?? []).map((r) => rowFrom(r, TOWED_FIELDS)));

  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);

  function setSingleField(code: string, key: string, v: string) {
    setSingle((prev) => ({ ...prev, [code]: { ...prev[code], [key]: v } }));
  }

  /** Assemble the full structured payload from current form state. */
  function buildBody(): InvestigationWrite {
    const body: InvestigationWrite = {
      case_number: header.case_number || null,
      inspection_number: header.inspection_number || null,
      officer_name: header.officer_name || null,
      officer_id: header.officer_id || null,
      post_crash_date: header.post_crash_date || null,
      has_hazmat: hasHazmat,
      has_additional_towed_units: hasTowed,
      // Replace-on-write repeating structures: send the full list every save.
      seating_positions: seating.map((r) => payloadFrom(r, SEATING_FIELDS)) as SeatingPositionData[],
      axles: axles.map((r) => payloadFrom(r, AXLE_FIELDS)) as AxleData[],
      tires: tires.map((r) => payloadFrom(r, TIRE_FIELDS)) as TireData[],
      trailers: trailers.map((r) => payloadFrom(r, TRAILER_FIELDS)) as TrailerData[],
      hazmat: hasHazmat ? (hazmat.map((r) => payloadFrom(r, HAZMAT_FIELDS)) as HazmatData[]) : [],
      additional_towed_units: hasTowed ? (towed.map((r) => payloadFrom(r, TOWED_FIELDS)) as AdditionalTowedUnitData[]) : [],
    };
    // Single-valued sections: send a section object only when it carries data, so
    // an untouched section stays untouched (PATCH leaves a missing section alone).
    for (const s of SINGLE_SECTIONS) {
      const row = single[s.code];
      if (rowHasValue(row, s.fields)) {
        (body as Record<string, unknown>)[s.attr] = payloadFrom(row, s.fields);
      }
    }
    return body;
  }

  async function save(): Promise<boolean> {
    setBusy(true); setError(null); setNotice(null);
    try {
      await sourceApi.updateInvestigation(crashId, record.id, buildBody());
      onSaved();
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Save failed');
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function saveOnly() {
    if (await save()) setNotice('Saved.');
  }

  async function submit() {
    // Persist first so submit validates the stored sections, then flip to SUBMITTED.
    if (!(await save())) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      await sourceApi.submitInvestigation(crashId, record.id);
      onSaved();
      onClose();
    } catch (e) {
      // Surface the API's required-field 400 message verbatim (PCI-3).
      setError(e instanceof ApiError ? e.message : 'Submit failed');
    } finally {
      setBusy(false);
    }
  }

  const isSubmitted = record.status === 'SUBMITTED';

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-4xl">
        <DialogHeader className="mb-0">
          <DialogTitle>
            {readOnly ? 'View' : 'Edit'} investigation{record.case_number ? ` · ${record.case_number}` : ''}
          </DialogTitle>
        </DialogHeader>
        <div className="-mr-6 max-h-[70vh] overflow-y-auto py-4 pr-6">
          {/* Header fields */}
          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-1.5"><Label>Case #</Label><Input value={header.case_number} disabled={readOnly} onChange={(e) => setHeader({ ...header, case_number: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Inspection #</Label><Input value={header.inspection_number} disabled={readOnly} onChange={(e) => setHeader({ ...header, inspection_number: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Officer name</Label><Input value={header.officer_name} disabled={readOnly} onChange={(e) => setHeader({ ...header, officer_name: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Officer ID</Label><Input value={header.officer_id} disabled={readOnly} onChange={(e) => setHeader({ ...header, officer_id: e.target.value })} /></div>
            <div className="space-y-1.5"><Label>Post-crash date</Label><Input type="date" value={header.post_crash_date} disabled={readOnly} onChange={(e) => setHeader({ ...header, post_crash_date: e.target.value })} /></div>
          </div>

          <Tabs defaultValue={SECTION_TABS[0].value}>
            <TabsList className="max-w-full overflow-x-auto">
              {SECTION_TABS.map((t) => (
                <TabsTrigger key={t.value} value={t.value}>{t.label}</TabsTrigger>
              ))}
            </TabsList>

            {SINGLE_SECTIONS.map((s) => (
              <TabsContent key={s.code} value={s.code}>
                <SectionGrid
                  fields={s.fields}
                  row={single[s.code]}
                  setField={(key, v) => setSingleField(s.code, key, v)}
                  required={requiredBySection[s.code] ?? new Set()}
                  readOnly={readOnly}
                />
              </TabsContent>
            ))}

            <TabsContent value="SEATING">
              <RepeatingSection label="Seating position" fields={SEATING_FIELDS} rows={seating} setRows={setSeating} readOnly={readOnly} />
            </TabsContent>
            <TabsContent value="AXLES">
              <RepeatingSection label="Axle" fields={AXLE_FIELDS} rows={axles} setRows={setAxles} readOnly={readOnly} />
            </TabsContent>
            <TabsContent value="TIRES">
              <RepeatingSection label="Tire" fields={TIRE_FIELDS} rows={tires} setRows={setTires} readOnly={readOnly} />
            </TabsContent>
            <TabsContent value="TRAILERS">
              <RepeatingSection label="Trailer" fields={TRAILER_FIELDS} rows={trailers} setRows={setTrailers} readOnly={readOnly} />
            </TabsContent>

            <TabsContent value="CONDITIONAL">
              <div className="space-y-6">
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Checkbox checked={hasHazmat} disabled={readOnly} onChange={(e) => setHasHazmat(e.target.checked)} />
                    <Label>Hazmat present on this crash</Label>
                  </div>
                  {hasHazmat ? (
                    <RepeatingSection label="Hazmat unit" fields={HAZMAT_FIELDS} rows={hazmat} setRows={setHazmat} readOnly={readOnly} />
                  ) : (
                    <p className="text-sm text-muted-foreground">Enable the toggle to capture hazmat units.</p>
                  )}
                </div>
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Checkbox checked={hasTowed} disabled={readOnly} onChange={(e) => setHasTowed(e.target.checked)} />
                    <Label>Additional towed units present</Label>
                  </div>
                  {hasTowed ? (
                    <RepeatingSection label="Towed unit" fields={TOWED_FIELDS} rows={towed} setRows={setTowed} readOnly={readOnly} />
                  ) : (
                    <p className="text-sm text-muted-foreground">Enable the toggle to capture additional towed units.</p>
                  )}
                </div>
              </div>
            </TabsContent>

            <TabsContent value="ELD">
              <EldSummarySection crashId={crashId} readOnly={readOnly} />
            </TabsContent>
          </Tabs>

          {error ? <p className="mt-4 whitespace-pre-wrap text-sm text-destructive">{error}</p> : null}
          {notice ? <p className="mt-4 text-sm text-emerald-600">{notice}</p> : null}
        </div>
        <DialogFooter className="mt-0">
          <Button variant="outline" onClick={onClose} disabled={busy}>Close</Button>
          {!readOnly ? (
            <>
              <Button variant="outline" onClick={saveOnly} disabled={busy}>Save</Button>
              {!isSubmitted ? (
                <Button onClick={submit} disabled={busy}><Send className="h-4 w-4" /> Save & submit</Button>
              ) : null}
            </>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Re-export the §19.2 single-valued section codes for any caller that wants them.
export const PCI_SECTION_CODES = SINGLE_SECTIONS.map((s) => s.code);
