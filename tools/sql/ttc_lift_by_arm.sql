-- Voting study: catch rate at one reviewer vs nine, per arm. Independent copies climb; correlated copies stay flat; below-chance copies fall.
select a.arm, a.detectable_catch as k1, b.detectable_catch as k9, round(b.detectable_catch - a.detectable_catch, 4) as lift
from ttc_curve a join ttc_curve b on a.arm = b.arm and a.k = 1 and b.k = 9 order by lift desc;
