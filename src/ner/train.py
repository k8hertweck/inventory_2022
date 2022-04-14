#!/usr/bin/env python3
"""
Purpose: Train NER model from pretrained BERT
Authors: Ana-Maria Istrate and Kenneth Schackart
"""

from datasets import load_metric
import numpy as np
from transformers import AutoModelForTokenClassification, get_scheduler
from torch.optim import AdamW
from torch.utils.data import DataLoader
from tqdm.auto import tqdm
import torch
import argparse
import copy
import plotly.express as px
from utils import *
from ner_data_handler import *
import os


class Trainer():
    """
  Handles training of the model
  """
    def __init__(self, model, optimizer, train_dataloader, val_dataloader,
                 lr_scheduler, num_epochs, num_training_steps, device):
        """
    :param model: PyTorch model
    :param optimizer: optimizer used
    :param train_dataloader: DataLoader containing data used for training
    :param val_dataloader: DataLoader containing data used for validation
    :param lr_scheduler: learning rate scheduler; could be equal to None if no lr_scheduler is used
    :param num_epochs: number of epochs to train the model for
    :param num_training_steps: total number of training steps
    :param device: device used for training; equal to 'cuda' if GPU is available
    """
        self.model = model
        self.optimizer = optimizer
        self.train_dataloader = train_dataloader
        self.val_dataloader = val_dataloader
        self.lr_scheduler = lr_scheduler
        self.num_epochs = num_epochs
        self.num_training_steps = num_training_steps
        self.device = device

    def evaluate(self, dataloader):
        """
    Computes and returns metrics (P, R, F1 score, loss) of a model on data present in a dataloader
    :param dataloader: DataLoader containing tokenized text entries and corresponding labels
    :return: precision, recall, F1 score, loss
    """
        metric = load_metric("seqeval")
        total_loss = 0
        num_seen_datapoints = 0

        for batch in dataloader:
            batch = {k: v.to(device) for k, v in batch.items()}
            with torch.no_grad():
                outputs = self.model(**batch)
            num_seen_datapoints += len(batch['input_ids'])
            logits = outputs.logits
            predictions = logits.argmax(dim=-1)
            loss = outputs.loss

            labels = batch["labels"]
            pred_labels, true_labels = self.postprocess(predictions, labels)
            metric.add_batch(predictions=pred_labels, references=true_labels)

            total_loss += loss.item()
        total_loss /= num_seen_datapoints
        results = metric.compute()
        p, r, f1, _ = self.get_metrics(results)
        return p, r, f1, total_loss

    def train_epoch(self, progress_bar):
        """
    Handles training of the model over one epoch
    :param progress_bar: tqdm instance for tracking progress
    """
        train_loss = 0
        num_train = 0
        for batch in self.train_dataloader:
            batch = {k: v.to(device) for k, v in batch.items()}
            num_train += len(batch['input_ids'])
            outputs = self.model(**batch)
            loss = outputs.loss
            loss.backward()
            train_loss += loss.item()

            self.optimizer.step()
            if self.lr_scheduler:
                self.lr_scheduler.step()
            self.optimizer.zero_grad()
            progress_bar.update(1)

        return train_loss / num_train

    def train(self):
        """
    Handles training of the model over all epochs
    """
        progress_bar = tqdm(range(num_training_steps))
        self.model.train()

        best_model = self.model
        best_val_f1_score = 0
        best_epoch = -1
        train_losses = []
        val_losses = []
        for epoch in range(self.num_epochs):
            train_loss = 0
            # Training
            train_loss = self.train_epoch(progress_bar)
            train_losses.append(train_loss)

            # Evaluation
            self.model.eval()
            train_p, train_r, train_f1, _ = self.evaluate(
                self.train_dataloader)
            val_p, val_r, val_f1, val_loss = self.evaluate(self.val_dataloader)

            if val_f1 > best_val_f1_score:
                best_model = copy.deepcopy(self.model)
                best_val_f1_score = val_f1
                best_epoch = epoch

            val_losses.append(val_loss)
            print(
                "Epoch", (epoch + 1),
                ": Train Loss: %.5f Precision: %.3f Recall: %.3f F1: %.3f || Val Loss: %.5f Precision: %.3f Recall: %.3f F1: %.3f"
                % (train_loss, train_p, train_r, train_f1, val_loss, val_p,
                   val_r, val_f1))
        self.best_model = best_model
        self.best_epoch = best_epoch
        self.best_f1_score = best_val_f1_score
        return best_model, best_epoch, best_val_f1_score, train_losses, val_losses

    def get_metrics(self, results):
        """
    Return metrics (Precision, recall, f1, accuracy)
    """
        return [
            results[f"overall_{key}"]
            for key in ["precision", "recall", "f1", "accuracy"]
        ]

    def postprocess(self, predictions, labels):
        """
    Postprocess true and predicted arrays (as indices) to the corresponding labels (eg 'B-RES', 'I-RES')
    :param predictions: array corresponding to predicted labels (as indices)
    :param labels: array corresponding to true labels (as indices)
    :return: predicted and true labels (as tags)
    """
        predictions = predictions.detach().cpu().clone().numpy()
        labels = labels.detach().cpu().clone().numpy()
        true_labels = [[ID2NER_TAG[l] for l in label if l != -100]
                       for label in labels]
        pred_labels = [[
            ID2NER_TAG[p] for (p, l) in zip(prediction, label) if l != -100
        ] for prediction, label in zip(predictions, labels)]
        return pred_labels, true_labels

    def save_best_model(self, checkpt_filename):
        """
    Saves a model checkpoint, epoch and F1 score to file
    :param checkpt_filename: filename under which the model checkpoint will be saved
    """
        torch.save(
            {
                'model_state_dict': self.best_model.state_dict(),
                'epoch': self.best_epoch,
                'f1_val': self.best_f1_score,
            }, checkpt_filename)

    def plot_losses(self, losses, labels, img_filename):
        """
    Plots training and val losses
    :param num_epochs: total number of epochs the model was trained on; corresponds to length of the losses array
    :param losses: array corresponding to [train_losses, val_losses]
    :param img_filename: filename under which to save the image
    :return: Generated plot
    """
        x = [i for i in range(self.num_epochs)]
        df = pd.DataFrame({'Epoch': x})
        for loss_arr, label in zip(losses, labels):
            df[label] = loss_arr
        fig = px.line(df, x="Epoch", y=labels, title='Train/Val Losses')
        fig.show()
        fig.write_image(img_filename)
        return fig


if __name__ == '__main__':
    # Parsing arguments
    parser = argparse.ArgumentParser()

    parser.add_argument('--num_epochs',
                        type=int,
                        default=3,
                        help='Number of Epochs')
    parser.add_argument('--batch-size',
                        type=int,
                        default=16,
                        help='Batch Size')
    parser.add_argument('--learning-rate',
                        type=float,
                        default=3e-5,
                        help='Learning Rate')
    parser.add_argument('--weight_decay',
                        type=float,
                        default=0.01,
                        help='Weight Decay for Learning Rate')
    parser.add_argument(
        '--lr_scheduler',
        action='store_true',
        help=
        'True if using a Learning Rate Scheduler. More info here: https://huggingface.co/docs/transformers/main_classes/optimizer_schedules'
    )
    parser.add_argument(
        '--use-default-values',
        type=bool,
        default=True,
        help='True if to use default values available in ner_utils.py')
    parser.add_argument(
        '--model_name',
        type=str,
        default='biomed_roberta',
        help=
        "Name of model to try. Can be one of: ['bert', 'biobert', 'scibert', 'pubmedbert', 'pubmedbert_pmc', 'bluebert', 'bluebert_mimic3', 'sapbert', 'sapbert_mean_token', 'bioelectra', 'bioelectra_pmc', 'electramed', 'biomed_roberta', 'biomed_roberta_chemprot', 'biomed_roberta_rct_500']"
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='checkpts',
        help='Default directory to output checkpt and plot losses')
    parser.add_argument(
        '--train_file',
        type=str,
        default='data/ner_train.pkl',
        help=
        'Location of training file. Note that it has to be in a .pkl format')
    parser.add_argument(
        '--val_file',
        type=str,
        default='data/ner_val.pkl',
        help='Location of val file. Note that it has to be in a .pkl format')
    parser.add_argument(
        '--test_file',
        type=str,
        default='data/ner_test.pkl',
        help='Location of test file. Note that it has to be in a .pkl format')
    parser.add_argument(
        '--sanity-check',
        action='store_true',
        help=
        "True for sanity-check. Runs training on a smaller subset of the entire training data."
    )

    args, _ = parser.parse_known_args()

    if args.use_default_values:
        model_name = args.model_name
        args.model_checkpoint = ARGS_MAP[model_name][0]
        args.batch_size = ARGS_MAP[model_name][1]
        args.learning_rate = ARGS_MAP[model_name][2]
        args.weight_decay = ARGS_MAP[model_name][3]
        args.use_scheduler = ARGS_MAP[model_name][4]
    print(f'args={args}')

    if not os.path.exists(args.output_dir):
        os.mkdir(args.output_dir)

    # Train, val, test dataloaders generation
    print('Generating train, val, test dataloaders ...')
    print('=' * 30)

    model_huggingface_version = ARGS_MAP[args.model_name][0]
    data_handler = NERDataHandler(model_huggingface_version, args.batch_size,
                                  args.train_file, args.val_file,
                                  args.test_file, args.sanity_check)
    train_dataloader, val_dataloader, test_dataloader = data_handler.get_dataloaders(
    )

    print('Finished generating dataloaders!')
    print('=' * 30)

    # Model Initialization
    print('Initializing', model_huggingface_version, 'model ...')
    print('=' * 30)
    set_random_seed(45)
    model = AutoModelForTokenClassification.from_pretrained(
        model_huggingface_version, id2label=ID2NER_TAG, label2id=NER_TAG2ID)
    optimizer = AdamW(model.parameters(),
                      lr=args.learning_rate,
                      weight_decay=args.weight_decay)
    num_training_steps = args.num_epochs * len(train_dataloader)
    device = torch.device(
        "cuda") if torch.cuda.is_available() else torch.device("cpu")
    if args.lr_scheduler:
        lr_scheduler = get_scheduler("linear",
                                     optimizer=optimizer,
                                     num_warmup_steps=0,
                                     num_training_steps=num_training_steps)
    else:
        lr_scheduler = None
    model.to(device)

    # Model Training
    print('Starting model training...')
    print('=' * 30)
    trainer = Trainer(model, optimizer, train_dataloader, val_dataloader,
                      lr_scheduler, args.num_epochs, num_training_steps,
                      device)
    best_model, best_epoch, best_val_f1_score, train_losses, val_losses = trainer.train(
    )

    # Save best checkpoint
    checkpt_filename = args.output_dir + 'checkpt_ner_' + args.model_name + '_' + str(
        best_epoch + 1) + '_epochs'
    trainer.save_best_model(checkpt_filename)
    print('Saved best checkpt to', checkpt_filename)

    # Plot losses
    img_filename = args.output_dir + args.model_name + '_' + str(
        best_epoch + 1) + '_epochs.png'
    trainer.plot_losses([train_losses, val_losses], ['Train Loss', 'Val Loss'],
                        img_filename)
    print('=' * 30)
