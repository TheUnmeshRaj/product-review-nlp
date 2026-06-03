-- fun.lua — playful Lua demo for Review Intelligence workspace
-- Shows a tiny ASCII feature-summary to try Lua

local features = {
  {name = "display", positive = 10, negative = 90, mentions = 2},
  {name = "performance", positive = 20, negative = 80, mentions = 1},
  {name = "price", positive = 15, negative = 85, mentions = 6},
  {name = "camera", positive = 58, negative = 42, mentions = 12},
}

local function bar(pct, width)
  width = width or 20
  local filled = math.floor((pct/100) * width)
  return string.rep("#", filled) .. string.rep("-", width - filled)
end

print("=== Review Intelligence — Lua Demo ===\n")
for _, f in ipairs(features) do
  local tone = f.positive >= f.negative and "👍" or "👎"
  print(string.format("%s  %s", tone, string.upper(f.name)))
  print("  Sentiment Split:")
  print(string.format("    + %3d%% |%s|", f.positive, bar(f.positive)))
  print(string.format("    - %3d%% |%s|", f.negative, bar(f.negative)))
  print(string.format("  Mentions: %d  •  Score: %d reviews", f.mentions, f.mentions))
  print("  Sample: \"(sample review snippet)\"\n")
end

print("Tip: Run with 'lua fun.lua' if you have Lua installed.")
