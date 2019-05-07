scraping parts forked and adjusted from http://quotes.toscrape.com ([github repo](https://github.com/scrapinghub/spidyquotes)).


#### Running

    python scrape_and_label.py --scrape --delay 10 --recalc


#### ideas / todo
    eng:
        refactor configuration and search url (to support multiple kinds of searches)
        web frontend django / jupyter
        tests
        
        
    algo:
        summary / sentiment:
            https://elitedatascience.com/python-nlp-libraries
            https://www.reddit.com/r/datascience/comments/8qde2g/sentiment_analysis_in_python_any_pretrained_models/
            http://nlp.town/blog/off-the-shelf-sentiment-analysis/  
        model improvement:
            only user NER words
            w2v / sent2vec
            self-supervision (title prediction) pretraining
    
        experiement with ways to handle the imbalance (weights for regression?)    
        separate tuning and refitting
        
    data:
        other sites (indeed, linked in)
