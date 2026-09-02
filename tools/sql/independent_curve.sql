-- The full k-curve for independent copies - the friendly case the study itself calls the upper line.
select k, detectable_catch, detectable_hits, detectable_reviews from ttc_curve where arm = 'independent' order by k;
