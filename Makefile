
.PHONY: deploy check

check:
	rm -rf dist 
	python3 -m build
	twine check dist/*

deploy:
	rm -rf dist 
	python3 -m build
	twine upload dist/*
