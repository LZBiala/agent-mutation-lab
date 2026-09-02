-- The headline: planted defects caught at the planted line, out of all planted.
select sum(hits) as caught, sum(hits)+sum(misses) as planted, round(1.0*sum(hits)/(sum(hits)+sum(misses)),4) as catch_rate from class_metrics;
