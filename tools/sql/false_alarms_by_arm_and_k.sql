-- False alarms per clean review as the vote grows: does majority voting also suppress invented findings?
select arm, k, false_alarms, clean_reviews, fa_per_clean_review from ttc_curve order by arm, k;
