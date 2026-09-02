-- The class the bundled reviewer cannot see - left in on purpose so the scorecard shows a real miss.
select class_id, misses from class_metrics where hits = 0 and misses > 0;
