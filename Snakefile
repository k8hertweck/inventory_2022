import pandas as pd

# Import tab separated file containined the configurations
# used for training each model.
model_df = pd.read_table(config["models"]).set_index("model", drop=True)
model_df = model_df.fillna("")


rule all:
    input:
        "data/full_corpus_predictions/predicted_positives.csv",
        "data/full_corpus_predictions/ner/predictions.csv"


# Split curated classification set into train, val, and test
rule split_classif_data:
    input:
        config["classif_data"],
    output:
        config["classif_splits_dir"] + "/train_paper_classif.csv",
        config["classif_splits_dir"] + "/val_paper_classif.csv",
        config["classif_splits_dir"] + "/test_paper_classif.csv",
    params:
        out_dir=config["classif_splits_dir"],
    shell:
        """
        python3 class_data_generator.py \
            -o {params.out_dir} \
            -r \
            {input}
        """


# Train each classifier
rule train_classif:
    input:
        train=config["classif_splits_dir"] + "/train_paper_classif.csv",
        val=config["classif_splits_dir"] + "/val_paper_classif.csv",
    output:
        config["classif_train_outdir"] + "/{model}/checkpt.pt",
        config["classif_train_outdir"] + "/{model}/train_stats.csv",
    params:
        out_dir=config["classif_train_outdir"],
        epochs=config["classif_epochs"],
        hf_model=lambda w: model_df.loc[w.model, "hf_name"],
        batch_size=lambda w: model_df.loc[w.model, "batch_size"],
        learn_rate=lambda w: model_df.loc[w.model, "learning_rate"],
        weight_decay=lambda w: model_df.loc[w.model, "weight_decay"],
        scheduler_flag=lambda w: model_df.loc[w.model, "scheduler"],
    log:
        config["classif_log_dir"] + "/{model}.log",
    benchmark:
        config["classif_benchmark_dir"] + "/{model}.txt"
    shell:
        """
        (python3 src/class_train.py \
            -m {params.hf_model} \
            -ne {params.epochs} \
            -t {input.train} \
            -v {input.val} \
            -o {params.out_dir} \
            -batch {params.batch_size} \
            -rate {params.learn_rate} \
            -decay {params.weight_decay} \
            -r \
            {params.scheduler_flag}
        )2> {log}
        """


# Select best trained classifier based on validation F1 score
rule find_best_classifier:
    input:
        expand(
            "{d}/{model}/train_stats.csv",
            d=config["classif_train_outdir"],
            model=model_df.index,
        ),
    output:
        config["classif_train_outdir"] + "/best/*/best_checkpt.pt",
        config["classif_train_outdir"] + "/best/*/combined_stats.csv",
    params:
        out_dir=config["classif_train_outdir"] + "/best",
    shell:
        """
        python3 model_picker.py \
            -o {params.out_dir} \
            {input}
        """

# Predict classification of entire corpus
rule classify_full_corpus:
    input:
        classifier=config["classif_train_outdir"] + "/best/*/best_checkpt.pt",
        infile=config["full_corpus"],
    output:
         "data/full_corpus_predictions/classification/predictions.csv",
    params:
        out_dir="data/full_corpus_predicted_classification",
    shell:
        """
        python3 class_predict.py \
            -o {params.out_dir} \
            -c {input.classifier} \
            -i {input.infile}
        """


# Filter out only predicted biodata resources
rule filter_positives:
    input:
        "data/full_corpus_predictions/classification/predictions.csv",
    output:
        "data/full_corpus_predictions/predicted_positives.csv",
    shell:
        """
        head -n 1 > {output}
        grep 'biodata-resource' >> {output}
        """


# Split curated NER set into train, val, and test
rule split_ner_data:
    input:
        config["ner_data"],
    output:
        config["ner_splits_dir"] + "/train_ner.csv",
        config["ner_splits_dir"] + "/val_ner.csv",
        config["ner_splits_dir"] + "/test_ner.csv",
        config["ner_splits_dir"] + "/train_ner.pkl",
        config["ner_splits_dir"] + "/val_ner.pkl",
        config["ner_splits_dir"] + "/test_ner.pkl",
    params:
        out_dir=config["ner_splits_dir"],
    shell:
        """
        python3 ner_data_generator.py \
            -o {params.out_dir} \
            -r \
            {input}
        """


# Train each NER model
rule train_ner:
    input:
        train=config["ner_splits_dir"] + "/train_ner.pkl",
        val=config["ner_splits_dir"] + "/val_ner.pkl",
    output:
        config["ner_train_outdir"] + "/{model}/checkpt.pt",
        config["ner_train_outdir"] + "/{model}/train_stats.csv",
    params:
        out_dir=config["ner_train_outdir"],
        epochs=config["ner_epochs"],
        hf_model=lambda w: model_df.loc[w.model, "hf_name"],
        batch_size=lambda w: model_df.loc[w.model, "batch_size"],
        learn_rate=lambda w: model_df.loc[w.model, "learning_rate"],
        weight_decay=lambda w: model_df.loc[w.model, "weight_decay"],
        scheduler_flag=lambda w: model_df.loc[w.model, "scheduler"],
    log:
        config["ner_log_dir"] + "/{model}.log",
    benchmark:
        config["ner_benchmark_dir"] + "/{model}.txt"
    shell:
        """
        (python3 src/ner_train.py \
            -m {params.hf_model} \
            -ne {params.epochs} \
            -t {input.train} \
            -v {input.val} \
            -o {params.out_dir} \
            -batch {params.batch_size} \
            -rate {params.learn_rate} \
            -decay {params.weight_decay} \
            -r \
            {params.scheduler_flag}
        )2> {log}
        """


# Select best NER model based on validation F1 score
rule find_best_ner:
    input:
        expand(
            "{d}/{model}/train_stats.csv",
            d=config["ner_train_outdir"],
            model=model_df.index,
        ),
    output:
        config["ner_train_outdir"] + "/best/*/best_checkpt.pt",
        config["ner_train_outdir"] + "/best/*/combined_stats.csv",
    params:
        out_dir=config["ner_train_outdir"] + "/best",
    shell:
        """
        python3 model_picker.py \
            -o {params.out_dir} \
            {input}
        """


# Predict NER on full corpus
rule ner_full_corpus:
    input:
        classifier=config["ner_train_outdir"] + "/best/*/best_checkpt.pt",
        infile=config["full_corpus"],
    output:
         "data/full_corpus_predictions/ner/predictions.csv",
    params:
        out_dir="data/full_corpus_predicted/ner",
    shell:
        """
        python3 ner_predict.py \
            -o {params.out_dir} \
            -c {input.classifier} \
            -i {input.infile}
        """