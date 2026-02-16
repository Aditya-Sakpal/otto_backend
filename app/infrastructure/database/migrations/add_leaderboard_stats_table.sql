-- Leaderboard accumulator table (pre-aggregated cache per rep per period)
-- See context.md: leaderboard_stats for design
CREATE TABLE IF NOT EXISTS leaderboard_stats (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    period_key VARCHAR(20) NOT NULL,
    won_count INTEGER NOT NULL DEFAULT 0,
    total_resolved INTEGER NOT NULL DEFAULT 0,
    sum_deal_value DOUBLE PRECISION NOT NULL DEFAULT 0,
    no_show_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, company_id, period_key)
);

CREATE INDEX IF NOT EXISTS idx_leaderboard_stats_company_period ON leaderboard_stats(company_id, period_key);
