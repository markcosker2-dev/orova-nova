import Phaser from 'phaser';
import ProceduralAssets from '../utils/ProceduralAssets';

export default class Level1 extends Phaser.Scene {
    constructor() {
        super('Level1');
    }

    preload() {
        this.load.image('tile', 'assets/tile.png');
        this.load.svg('dolphin', 'assets/dolphin.svg');
        this.load.svg('item_flour', 'assets/flour.svg');
        this.load.svg('item_sugar', 'assets/sugar.svg');
        this.load.svg('item_butter', 'assets/butter.svg');
        this.load.svg('item_blueberries', 'assets/blueberries.svg');
    }

    create() {
        // Tile background
        this.add.tileSprite(400, 300, 800, 600, 'tile').setAlpha(0.6);

        // Player
        this.player = this.physics.add.sprite(400, 300, 'dolphin');
        this.player.setCollideWorldBounds(true);
        this.player.setScale(0.8);

        // Ingredients
        this.ingredients = this.physics.add.group();
        const locations = [
            { x: 150, y: 150, tex: 'item_flour', name: 'Flour' },
            { x: 650, y: 150, tex: 'item_sugar', name: 'Sugar' },
            { x: 150, y: 450, tex: 'item_butter', name: 'Butter' },
            { x: 650, y: 450, tex: 'item_blueberries', name: 'Blueberries' }
        ];

        locations.forEach(loc => {
            const item = this.ingredients.create(loc.x, loc.y, loc.tex);
            item.name = loc.name;
            item.setScale(0.6);
            // Add subtle glow
            this.add.circle(loc.x, loc.y, 40, 0xffffff, 0.2);
        });

        // Controls
        this.cursors = this.input.keyboard.createCursorKeys();

        // Dialogue
        this.time.delayedCall(500, () => {
            this.showDialogue("Welcome to the Blueberry Adventure! ❤️\nHelp the dolphin collect ingredients for the cake.");
            this.time.delayedCall(3000, () => {
                this.showDialogue("Remember when you pretended not to see me?\nAt the bus terminal...");
            });
        });

        // Physics
        this.physics.add.overlap(this.player, this.ingredients, this.collectIngredient, null, this);
        
        this.collectedCount = 0;
    }

    update() {
        this.player.setVelocity(0);
        const speed = 200;

        if (this.cursors.left.isDown) {
            this.player.setVelocityX(-speed);
            this.player.flipX = true;
        } else if (this.cursors.right.isDown) {
            this.player.setVelocityX(speed);
            this.player.flipX = false;
        }

        if (this.cursors.up.isDown) this.player.setVelocityY(-speed);
        else if (this.cursors.down.isDown) this.player.setVelocityY(speed);
    }

    collectIngredient(player, ingredient) {
        ingredient.disableBody(true, true);
        this.collectedCount++;
        
        if (this.collectedCount === 4) {
            this.showDialogue("Blueberry cake complete!\nLevel 2 Unlocked.");
            this.cameras.main.fadeOut(1000, 0, 0, 0);
            this.time.delayedCall(1500, () => {
                this.scene.start('Level2');
            });
        }
    }

    showDialogue(text) {
        this.events.emit('show-dialogue', text);
    }
}
