-- Create the ENUM type for tags if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'post_tags') THEN
        CREATE TYPE post_tags AS ENUM ('agenda_setting', 'objection_handling');
    END IF;
END $$;

-- Create the posts table if it doesn't exist
CREATE TABLE IF NOT EXISTS posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appointment_id UUID NOT NULL,
    poster_id UUID NOT NULL,
    note TEXT,
    tags post_tags,
    likes INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key constraints
    CONSTRAINT fk_appointment
        FOREIGN KEY (appointment_id)
        REFERENCES appointments(id)
        ON DELETE CASCADE,
    
    CONSTRAINT fk_poster
        FOREIGN KEY (poster_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_posts_appointment_id ON posts(appointment_id);
CREATE INDEX IF NOT EXISTS idx_posts_poster_id ON posts(poster_id);