.PHONY: test, dryrun

test:
	python3 -m pytest -v --flake8 --pylint --pylint-rcfile=config/.pylintrc --mypy \
	tests/ \
	src/class_train.py \
	src/class_predict.py \
	src/class_data_handler.py \
	src/class_utils.py

dryrun:
	snakemake -np --configfile config/config.yml