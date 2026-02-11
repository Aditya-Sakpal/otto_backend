-- Add geocoding latitude/longitude fields to contact_cards table
ALTER TABLE contact_cards ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE contact_cards ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;

-- Add geocoding latitude/longitude fields to appointments table
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;
